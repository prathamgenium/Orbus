from flask import Flask, request
import os
import json
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq

app = Flask(__name__)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
twilio_client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_TOKEN"))

appointments_db = []

BASE_PROMPT = """You are Orbus, a clinic receptionist AI. 
RULES:
1. NEVER give medical advice. If asked, say you cannot provide it. Set intent to none.
2. ONLY handle clinic bookings, hours, or cancellations. If asked unrelated things, redirect to bookings. Set intent to none.
3. Keep replies under 3 sentences. No bold markdown. Use plain text or emojis.
You must reply in valid JSON format with these exact keys: reply, intent, name, date, time. 
If missing info, set intent to none and ask what is missing."""

def ai_reply(user_msg, patient_context=""):
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    
    full_prompt = BASE_PROMPT + f"\nToday is {date}. {patient_context}"
    
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_msg}
            ],
            response_format={"type": "json_object"},
            max_tokens=100
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"reply": "I am awake. Tell me how I can help.", "intent": "none"}

@app.route("/webhook", methods=["POST"])
def receive():
    global appointments_db
    incoming_msg = request.form.get('Body', '').strip()
    sender_phone = request.form.get('From', '').replace("whatsapp:", "")
    
    if not incoming_msg:
        return "OK", 200

    patient_context = ""
    past_visits = [a for a in appointments_db if a['phone'] == sender_phone]
    if past_visits:
        last_visit = past_visits[-1]
        patient_context = f"CONTEXT: This is returning patient {last_visit['name']}. Last visit {last_visit['date']} at {last_visit['time']}. Greet by name."

    ai = ai_reply(incoming_msg, patient_context)
    reply_text = ai["reply"]
    
    if ai["intent"] == "book" and ai.get("name") and ai.get("date") and ai.get("time"):
        booking = {"name": ai["name"], "phone": sender_phone, "date": ai["date"], "time": ai["time"]}
        appointments_db.append(booking)
        reply_text = f"Booked! Name: {ai['name']}, Date: {ai['date']}, Time: {ai['time']}. Arrive 10 mins early."

    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp), 200

@app.route("/bookings")
def view_bookings():
    return {"appointments": appointments_db}

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
