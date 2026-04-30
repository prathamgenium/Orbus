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

SYSTEM_PROMPT = "You are Orbus, a clinic receptionist AI. NEVER give medical advice. ONLY handle clinic bookings. Keep replies under 3 sentences. You must reply in JSON with keys: reply, intent, name, date, time."

def ai_reply(user_msg, context=""):
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    full_prompt = SYSTEM_PROMPT + " Today is " + date_str + ". " + context
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
        return {"reply": "I am awake. How can I help?", "intent": "none"}

@app.route("/webhook", methods=["POST"])
def receive():
    global appointments_db
    incoming_msg = request.form.get('Body', '').strip()
    sender_phone = request.form.get('From', '').replace("whatsapp:", "")
    
    if not incoming_msg:
        return "OK", 200

    context = ""
    past = [a for a in appointments_db if a['phone'] == sender_phone]
    if past:
        last = past[-1]
        context = "This is returning patient " + last['name'] + ". Last visit " + last['date'] + " at " + last['time'] + ". Greet by name."

    ai = ai_reply(incoming_msg, context)
    reply_text = ai["reply"]
    
    intent = ai.get("intent")
    name = ai.get("name")
    date = ai.get("date")
    time = ai.get("time")

    if intent == "book" and name and date and time:
        booking = {"name": name, "phone": sender_phone, "date": date, "time": time}
        appointments_db.append(booking)
        reply_text = "Booked! Name: " + name + ", Date: " + date + ", Time: " + time + ". Arrive 10 mins early."

    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp), 200

@app.route("/bookings")
def view_bookings():
    return {"appointments": appointments_db}

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
