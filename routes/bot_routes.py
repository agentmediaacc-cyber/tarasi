
from flask import Blueprint, jsonify, request

bot_bp = Blueprint("bot", __name__)

@bot_bp.route("/api/bot/greeting")
def bot_greeting():
    return jsonify({
        "ok": True,
        "message": "Welcome to Tarasi Premium Transport"
    })

@bot_bp.route("/api/bot/message", methods=["POST"])
def bot_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    return jsonify({
        "ok": True,
        "reply": f"Tarasi AI received: {message}"
    })
