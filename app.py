from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from functools import wraps
import secrets

"""
Rental Property Management Web App
For managing rental properties with multi-owner support
"""

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rental_management.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class Owner(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    properties = db.relationship('Property', backref='owner', lazy=True)
    
class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500))
    property_type = db.Column(db.String(50))  # apartment, house, commercial
    bedrooms = db.Column(db.Integer)
    bathrooms = db.Column(db.Integer)
    area_sqft = db.Column(db.Float)
    monthly_rent = db.Column(db.Float)
    owner_id = db.Column(db.Integer, db.ForeignKey('owner.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tenants = db.relationship('Tenant', backref='property', lazy=True)
    expenses = db.relationship('Expense', backref='property', lazy=True)
    payments = db.relationship('Payment', backref='property', lazy=True)
    maintenance_requests = db.relationship('MaintenanceRequest', backref='property', lazy=True)

class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20), nullable=False)
    whatsapp_number = db.Column(db.String(20))
    lease_start = db.Column(db.Date)
    lease_end = db.Column(db.Date)
    security_deposit = db.Column(db.Float)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))  # cash, bank_transfer, online
    payment_type = db.Column(db.String(50))  # rent, security_deposit, maintenance
    status = db.Column(db.String(20), default='completed')  # pending, completed, failed
    notes = db.Column(db.Text)
    tenant = db.relationship('Tenant', backref='payments')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    category = db.Column(db.String(100))  # maintenance, utilities, taxes, insurance
    description = db.Column(db.Text)
    amount = db.Column(db.Float, nullable=False)
    expense_date = db.Column(db.Date, default=datetime.utcnow)
    vendor = db.Column(db.String(200))
    receipt_url = db.Column(db.String(500))
    
class MaintenanceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    issue_type = db.Column(db.String(100))  # plumbing, electrical, hvac, other
    description = db.Column(db.Text)
    priority = db.Column(db.String(20))  # low, medium, high, urgent
    status = db.Column(db.String(20), default='open')  # open, in_progress, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    tenant = db.relationship('Tenant', backref='maintenance_requests')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('owner.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('owner.id'))
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    document_type = db.Column(db.String(50))  # lease, insurance, inspection
    file_name = db.Column(db.String(200))
    file_url = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# Login manager
@login_manager.user_loader
def load_user(user_id):
    return Owner.query.get(int(user_id))

@app.context_processor
def inject_theme():
    # Example: Use session to store dark mode preference
    return dict(dark_mode=session.get('dark_mode', False))

@app.route('/toggle_dark_mode')
def toggle_dark_mode():
    session['dark_mode'] = not session.get('dark_mode', False)
    return redirect(request.referrer or url_for('dashboard'))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        
        # Check if user exists
        if Owner.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        # Create new owner
        hashed_password = generate_password_hash(password)
        new_owner = Owner(
            username=username,
            email=email,
            password_hash=hashed_password,
            phone=phone
        )
        db.session.add(new_owner)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        owner = Owner.query.filter_by(email=email).first()
        
        if owner and check_password_hash(owner.password_hash, password):
            login_user(owner)
            flash('Welcome back, {}!'.format(owner.username), 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get dashboard statistics
    total_properties = Property.query.filter_by(owner_id=current_user.id).count()
    active_tenants = db.session.query(Tenant).join(Property).filter(
        Property.owner_id == current_user.id,
        Tenant.is_active == True
    ).count()
    
    # Calculate monthly income
    monthly_income = db.session.query(db.func.sum(Property.monthly_rent)).filter_by(
        owner_id=current_user.id
    ).scalar() or 0
    
    # Recent payments
    recent_payments = db.session.query(Payment).join(Property).filter(
        Property.owner_id == current_user.id
    ).order_by(Payment.payment_date.desc()).limit(5).all()
    
    # Pending maintenance
    pending_maintenance = db.session.query(MaintenanceRequest).join(Property).filter(
        Property.owner_id == current_user.id,
        MaintenanceRequest.status != 'completed'
    ).count()
    
    return render_template('dashboard.html',
                         total_properties=total_properties,
                         active_tenants=active_tenants,
                         monthly_income=monthly_income,
                         recent_payments=recent_payments,
                         pending_maintenance=pending_maintenance)

@app.route('/properties')
@login_required
def properties():
    properties = Property.query.filter_by(owner_id=current_user.id).all()
    return render_template('properties.html', properties=properties)

@app.route('/add_property', methods=['GET', 'POST'])
@login_required
def add_property():
    if request.method == 'POST':
        new_property = Property(
            name=request.form.get('name'),
            address=request.form.get('address'),
            property_type=request.form.get('property_type'),
            bedrooms=int(request.form.get('bedrooms', 0)),
            bathrooms=int(request.form.get('bathrooms', 0)),
            area_sqft=float(request.form.get('area_sqft', 0)),
            monthly_rent=float(request.form.get('monthly_rent', 0)),
            owner_id=current_user.id
        )
        db.session.add(new_property)
        db.session.commit()
        flash('Property added successfully!', 'success')
        return redirect(url_for('properties'))
    
    return render_template('add_property.html')

@app.route('/tenants')
@login_required
def tenants():
    tenants = db.session.query(Tenant).join(Property).filter(
        Property.owner_id == current_user.id
    ).all()
    return render_template('tenants.html', tenants=tenants)

@app.route('/add_tenant', methods=['GET', 'POST'])
@login_required
def add_tenant():
    if request.method == 'POST':
        new_tenant = Tenant(
            name=request.form.get('name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            whatsapp_number=request.form.get('whatsapp_number'),
            lease_start=datetime.strptime(request.form.get('lease_start'), '%Y-%m-%d').date(),
            lease_end=datetime.strptime(request.form.get('lease_end'), '%Y-%m-%d').date(),
            security_deposit=float(request.form.get('security_deposit', 0)),
            property_id=int(request.form.get('property_id'))
        )
        db.session.add(new_tenant)
        db.session.commit()
        flash('Tenant added successfully!', 'success')
        return redirect(url_for('tenants'))
    
    properties = Property.query.filter_by(owner_id=current_user.id).all()
    return render_template('add_tenant.html', properties=properties)

@app.route('/payments')
@login_required
def payments():
    payments = db.session.query(Payment).join(Property).filter(
        Property.owner_id == current_user.id
    ).order_by(Payment.payment_date.desc()).all()
    return render_template('payments.html', payments=payments)

@app.route('/add_payment', methods=['GET', 'POST'])
@login_required
def add_payment():
    if request.method == 'POST':
        new_payment = Payment(
            property_id=int(request.form.get('property_id')),
            tenant_id=int(request.form.get('tenant_id')),
            amount=float(request.form.get('amount')),
            payment_date=datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date(),
            payment_method=request.form.get('payment_method'),
            payment_type=request.form.get('payment_type'),
            notes=request.form.get('notes')
        )
        db.session.add(new_payment)
        db.session.commit()
        flash('Payment recorded successfully!', 'success')
        return redirect(url_for('payments'))
    
    properties = Property.query.filter_by(owner_id=current_user.id).all()
    return render_template('add_payment.html', properties=properties)

@app.route('/expenses')
@login_required
def expenses():
    expenses = db.session.query(Expense).join(Property).filter(
        Property.owner_id == current_user.id
    ).order_by(Expense.expense_date.desc()).all()
    return render_template('expenses.html', expenses=expenses)

@app.route('/reports')
@login_required
def reports():
    # Generate financial reports
    return render_template('reports.html')

@app.route('/api/send_whatsapp_reminder', methods=['POST'])
@login_required
def send_whatsapp_reminder():
    # Integration point for WhatsApp Business API or Twilio
    # This would send rent reminders to tenants
    tenant_id = request.json.get('tenant_id')
    message = request.json.get('message')
    # Implement WhatsApp sending logic here
    return jsonify({'status': 'success', 'message': 'WhatsApp reminder sent'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
