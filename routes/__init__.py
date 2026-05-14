from .public_routes import public_bp
from .admin_routes import admin_bp

try:
    from .bot_routes import bot_bp
except Exception:
    bot_bp = None


def register_blueprints(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    if bot_bp:
        app.register_blueprint(bot_bp)
