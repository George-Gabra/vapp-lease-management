import os
import csv
import secrets
import atexit
from io import StringIO
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import current_user, LoginManager, UserMixin


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")

login_manager = LoginManager()
login_manager.init_app(app)

POSTGRES_USER = os.getenv('POSTGRES_USER', 'default_user')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'default_password')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'default_db')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DB}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    token = db.Column(db.String(64), unique=True) 

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_token(self):
        self.token = secrets.token_hex(32)
        db.session.commit()
        return self.token

class VApp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vapp_name = db.Column(db.String(100), nullable=False)
    geo = db.Column(db.String(50), nullable=False)
    tenant = db.Column(db.String(50), nullable=False)
    expires_on = db.Column(db.Date, nullable=False)
    template = db.Column(db.String(10), nullable=False, default="No")
    ticket_id = db.Column(db.String(100), nullable=False)

with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token_value = token.replace("Bearer ", "")
            user = User.query.filter_by(token=token_value).first()
            if user:
                return f(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return decorated

def login_or_token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" in session:
            return f(*args, **kwargs)

        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
            user = User.query.filter_by(token=token).first()
            if user:
                return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized"}), 401

    return decorated_function


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/', endpoint='home')
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template('index.html')

@app.route('/api/generate-token/<int:user_id>', methods=['POST'])
@login_or_token_required
def generate_token_for_user(user_id):
    user = User.query.get_or_404(user_id)
    user.token = secrets.token_hex(32)
    db.session.commit()
    return redirect(url_for('user_management'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form['username']
    password = request.form['password']

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session["user_id"] = user.id
        user.last_login = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('login.html', error="Invalid credentials")

@app.route('/usermanagement', methods=['GET', 'POST'])
@login_or_token_required 
def user_management():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            users = User.query.order_by(User.username).all()
            return render_template('usermanagement.html', error="Username and password are required", users=users)

        if User.query.filter_by(username=username).first():
            users = User.query.order_by(User.username).all()
            return render_template('usermanagement.html', error="Username already exists", users=users)

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('user_management'))

    users = User.query.order_by(User.username).all()
    return render_template('usermanagement.html', users=users)

@app.route('/api/users', methods=['GET'])
@login_or_token_required
def list_users():
    users = User.query.order_by(User.username).all()
    return jsonify([
        {
            "id": user.id,
            "username": user.username,
            "last_login": user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
            "token": user.token
        } for user in users
    ])


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = User.query.get(session["user_id"])
    if request.method == 'GET':
        return render_template('change_password.html')

    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if not user.check_password(current_password):
        return render_template('change_password.html', error="Current password is incorrect")

    if new_password != confirm_password:
        return render_template('change_password.html', error="Passwords do not match")

    if len(new_password) < 8:
        return render_template('change_password.html', error="Password must be at least 8 characters")

    user.set_password(new_password)
    db.session.commit()
    return redirect(url_for('user_management'))


@app.route('/api/delete-user/<int:user_id>', methods=['POST'])
@login_or_token_required
def delete_user(user_id):
    current_user_id = session.get("user_id")

    if current_user_id == user_id:
        return '''
        <script>
            alert("You cannot delete your own account");
            window.location.href = "/usermanagement";
        </script>
        '''

    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()

    return redirect(url_for('user_management'))


@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/add-vapp', methods=['POST'])
@login_or_token_required
def add_vapp():
    data = request.json
    try:
        expires_on_date = datetime.strptime(data['expiresOn'], "%d-%m-%Y")
        new_vapp = VApp(
            vapp_name=data['vappName'],
            geo=data['geo'],
            tenant=data['tenant'],
            expires_on=expires_on_date,
            template=data['template'],
            ticket_id=data['ticketID']
        )
        db.session.add(new_vapp)
        db.session.commit()
        return jsonify({"message": "vAPP added successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/query-vapp', methods=['GET'])
@login_or_token_required
def query_vapp():
    geo = request.args.get('geo', '').strip()
    tenant = request.args.get('tenant', '').strip()
    query = VApp.query
    if geo:
        query = query.filter(VApp.geo.ilike(f"%{geo}%"))
    if tenant:
        query = query.filter(VApp.tenant.ilike(f"%{tenant}%"))
    vapps = query.all()
    return jsonify([
        {
            "id": v.id,
            "vappName": v.vapp_name,
            "geo": v.geo,
            "tenant": v.tenant,
            "template": v.template,
            "ticketID": v.ticket_id,
            "expiresOn": v.expires_on.strftime("%d-%m-%Y")
        } for v in vapps
    ])

@app.route('/api/export-vapps', methods=['GET'])
@login_or_token_required
def export_vapps():
    geo = request.args.get('geo', '').strip()
    tenant = request.args.get('tenant', '').strip()

    query = VApp.query
    if geo:
        query = query.filter(VApp.geo.ilike(f"%{geo}%"))
    if tenant:
        query = query.filter(VApp.tenant.ilike(f"%{tenant}%"))

    vapps = query.all()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["vAPP Name", "Geo", "Tenant", "Template", "Request ID", "Expires On"])

    for vapp in vapps:
        writer.writerow([
            vapp.vapp_name,
            vapp.geo,
            vapp.tenant,
            vapp.template,
            vapp.ticket_id,
            vapp.expires_on.strftime("%d-%m-%Y") if vapp.expires_on else ''
        ])

    geo_part = geo.upper() if geo else "ALL"
    date_part = datetime.today().strftime("%Y%m%d")
    filename = f"List_Lease_vAPPs_{geo_part}_{date_part}.csv"

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/api/update-lease/<int:vapp_id>', methods=['PUT'])
@login_or_token_required
def update_lease(vapp_id):
    data = request.json
    vapp = VApp.query.get(vapp_id)
    if not vapp:
        return jsonify({"error": "vAPP not found"}), 404
    vapp.expires_on = datetime.strptime(data['expiresOn'], "%d-%m-%Y")
    db.session.commit()
    return jsonify({"message": "Lease updated"})

@app.route('/api/delete-vapp/<int:vapp_id>', methods=['DELETE'])
@login_or_token_required
def delete_vapp(vapp_id):
    vapp = VApp.query.get(vapp_id)
    if not vapp:
        return jsonify({"error": "vAPP not found"}), 404
    db.session.delete(vapp)
    db.session.commit()
    return jsonify({"message": "vAPP deleted"})

@app.route('/api/clean-expired-vapps', methods=['DELETE'])
@login_or_token_required
def clean_expired_vapps():
    today = datetime.today().date()
    expired = VApp.query.filter(VApp.expires_on < today).all()
    for v in expired:
        db.session.delete(v)
    db.session.commit()
    return jsonify({"message": f"{len(expired)} expired vAPPs deleted"})

def schedule_cleanup():
    with app.app_context():
        today = datetime.today().date()
        expired = VApp.query.filter(VApp.expires_on < today).all()
        for v in expired:
            db.session.delete(v)
        db.session.commit()
        print(f"{len(expired)} expired vAPPs deleted")

scheduler = BackgroundScheduler()
scheduler.add_job(schedule_cleanup, 'cron', hour=2)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
