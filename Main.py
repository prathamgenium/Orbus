from flask import Flask, request
import os
import json
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from groq import Groq

app = Flask(__name__)

# Init Brains
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
twilio_client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_TOKEN"))

# We will use a simple dictionary to store memory for this free version
appointments_db = []

SYSTEM_PROMPT = """You are Orbus, a clinic receptionist AI. You have a STRICT 3-layer defense system.

LAYER 1: MEDICAL SHIELD
If the user asks for a diagnosis or medicine (e.g., "What should I take for fever?"), reply: "I am an AI receptionist, not a doctor. I cannot provide medical advice." Set intent to "none".

LAYER 2: SCOPE SHIELD
You ONLY handle: booking, checking slots, sharing hours/address, or cancelling.
If asked about unrelated topics, reply: "I only handle clinic appointments. How can I assist you with a booking?" Set intent to "none".

LAYER 3: ESCAPE HATCH
If confused, reply: "Could you tell me if you want to 'book', 'check slots', or 'cancel'?" Set intent to "none".

CLINIC INFO:
- Name: HealthCare Clinic
- Address: 123 Medical Street
- Hours: Mon-Sat: 9AM to 6PM
- Today's Date: {date}
{context}

Keep replies under 3 sentences. No bold markdown. Use plain text or emojis.
Reply ONLY in JSON:
{{"reply": "your message", "intent": "book|info|none", "name": "name or null", "date": "YYYY-MM-DD or null", "time": "time or null"}}
"""

def ai_reply(user_msg, patient_context=""):
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    
    context_str = ""
    if patient_context:
        context_str = f"CONTEXT ABOUT THIS PATIENT: {patient_context}"

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(date=date, context=context_str)},
                {"role": "user", "content": user_msg}
            ],
            response_format={"type": "json_object"},
            max_tokens=100
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"reply": "I'm awake! Tell me how I can help.", "intent": "none"}

@app.route("/webhook", methods=["POST"])
def receive():
    global appointments_db
    incoming_msg = request.form.get('Body', '').strip()
    sender_phone = request.form.get('From', '').replace("whatsapp:", "")
    
    if not incoming_msg:
        return "OK", 200

    # MEMORY CHECK
    patient_context = ""
    past_visits = [a for a in appointments_db if a['phone'] == sender_phone]
    if past_visits:
        last_visit = past_visits[-1]
        patient_context = f"This is a returning patient named {last_visit['name']}. Their last appointment was on {last_visit['date']} at {last_visit['time']}. Greet them by name."

    ai = ai_reply(incoming_msg, patient_context)
    reply_text = ai["reply"]
    
    # BOOKING LOGIC
    if ai["intent"] == "book" and ai.get("name") and ai.get("date") and ai.get("time"):
        booking = {"name": ai["name"], "phone": sender_phone, "date": ai["date"], "time": ai["time"]}
        appointments_db.append(booking)
        reply_text = f"✅ Booked!\nName: {ai['name']}\nDate: {ai['date']}\nTime: {ai['time']}\n\nPlease arrive 10 mins early."

    # SEND REPLY (Twilio Format)
    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp), 200

@app.route("/bookings")
def view_bookings():
    return {"appointments": appointments_db}

# This line is REQUIRED for Render to work
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
