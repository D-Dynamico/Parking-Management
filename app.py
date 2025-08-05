from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, ParkingLot, ParkingSpot, ParkingReservation
from datetime import datetime
import os

app = Flask(__name__)

# Database configuration - using SQLite for simplicity
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Set up our extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    """Load a user by their ID for Flask-Login"""
    return User.query.get(int(user_id))

# Initialize the database and create a default admin user
with app.app_context():
    db.create_all()
    
    # Check if we need to create an admin user
    if not User.query.filter_by(role='admin').first():
        admin_password = generate_password_hash('admin123', method='pbkdf2:sha256')
        admin_user = User(username='admin', password=admin_password, role='admin')
        db.session.add(admin_user)
        db.session.commit()
        print("Created default admin user: username='admin', password='admin123'")

@app.route('/')
def index():
    """Home page - redirect users based on their role"""
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Basic validation
        if not username or not password:
            flash('Both username and password are required.', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('register.html')
        
        # Check if username is already taken
        if User.query.filter_by(username=username).first():
            flash('That username is already taken. Please choose another one.', 'error')
            return render_template('register.html')
        
        # Create the new user
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password, role='user')
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Something went wrong during registration. Please try again.', 'error')
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Make sure both fields are filled
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')
        
        # Find the user and check their password
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password, password):
            flash('Invalid login credentials. Please try again.', 'error')
            return render_template('login.html')
        
        # Log them in and redirect based on their role
        login_user(user)
        flash(f'Welcome back, {user.username}!', 'success')
        
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Log out the current user"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard with overview of the parking system"""
    # Make sure only admins can access this
    if current_user.role != 'admin':
        flash('Sorry, you need admin privileges to access that page.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Gather all the statistics we need
    parking_lots = ParkingLot.query.all()
    total_spots = ParkingSpot.query.count()
    occupied_spots = ParkingSpot.query.filter_by(status='O').count()
    available_spots = total_spots - occupied_spots
    total_users = User.query.filter_by(role='user').count()
    
    # Calculate total earnings from completed bookings
    completed_reservations = ParkingReservation.query.filter(
        ParkingReservation.leaving_timestamp.isnot(None)
    ).all()
    total_earnings = sum(reservation.total_cost or 0 for reservation in completed_reservations)
    
    # Get recent bookings for the dashboard
    recent_bookings = ParkingReservation.query.filter(
        ParkingReservation.leaving_timestamp.isnot(None)
    ).order_by(ParkingReservation.leaving_timestamp.desc()).limit(10).all()
    
    return render_template('admin_dashboard.html', 
                         parking_lots=parking_lots,
                         total_spots=total_spots,
                         occupied_spots=occupied_spots,
                         available_spots=available_spots,
                         total_users=total_users,
                         total_earnings=total_earnings,
                         recent_bookings=recent_bookings)

@app.route('/admin/create_lot', methods=['GET', 'POST'])
@login_required
def create_parking_lot():
    """Create a new parking lot"""
    # Admin only feature
    if current_user.role != 'admin':
        flash('Only administrators can create parking lots.', 'error')
        return redirect(url_for('user_dashboard'))
    
    if request.method == 'POST':
        # Get all the form data
        name = request.form.get('prime_location_name', '').strip()
        price = request.form.get('price', '')
        address = request.form.get('address', '').strip()
        pin_code = request.form.get('pin_code', '').strip()
        max_spots = request.form.get('maximum_number_of_spots', '')
        
        # Make sure all fields are filled out
        if not all([name, price, address, pin_code, max_spots]):
            flash('Please fill out all the required fields.', 'error')
            return render_template('create_lot.html')
        
        # Validate the numeric fields
        try:
            price = float(price)
            max_spots = int(max_spots)
            if price <= 0 or max_spots <= 0:
                raise ValueError("Values must be positive")
        except ValueError:
            flash('Price and number of spots must be positive numbers.', 'error')
            return render_template('create_lot.html')
        
        # Create the parking lot
        new_lot = ParkingLot(
            prime_location_name=name,
            price=price,
            address=address,
            pin_code=pin_code,
            maximum_number_of_spots=max_spots
        )
        
        try:
            db.session.add(new_lot)
            db.session.flush()  # This gets us the ID we need
            
            # Now create all the parking spots for this lot
            for spot_number in range(1, max_spots + 1):
                spot = ParkingSpot(
                    lot_id=new_lot.id,
                    spot_number=f"{new_lot.prime_location_name[:3].upper()}-{spot_number:03d}",
                    status='A'  # A = Available
                )
                db.session.add(spot)
            
            db.session.commit()
            flash(f'Successfully created "{name}" with {max_spots} parking spots!', 'success')
            return redirect(url_for('admin_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash('Something went wrong while creating the parking lot. Please try again.', 'error')
    
    return render_template('create_lot.html')

@app.route('/admin/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def edit_parking_lot(lot_id):
    """Edit an existing parking lot"""
    if current_user.role != 'admin':
        flash('Only administrators can edit parking lots.', 'error')
        return redirect(url_for('user_dashboard'))
    
    lot = ParkingLot.query.get_or_404(lot_id)
    
    if request.method == 'POST':
        # Update the lot with new information
        lot.prime_location_name = request.form.get('prime_location_name', '').strip()
        lot.price = float(request.form.get('price', 0))
        lot.address = request.form.get('address', '').strip()
        lot.pin_code = request.form.get('pin_code', '').strip()
        
        try:
            db.session.commit()
            flash('Parking lot information updated successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update the parking lot information.', 'error')
    
    return render_template('edit_lot.html', lot=lot)

@app.route('/admin/delete_lot/<int:lot_id>')
@login_required
def delete_parking_lot(lot_id):
    """Delete a parking lot (only if no spots are occupied)"""
    if current_user.role != 'admin':
        flash('Only administrators can delete parking lots.', 'error')
        return redirect(url_for('user_dashboard'))
    
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Safety check - don't delete if people are parked there
    occupied_spots = ParkingSpot.query.filter_by(lot_id=lot_id, status='O').count()
    if occupied_spots > 0:
        flash(f'Cannot delete this parking lot - {occupied_spots} spots are currently occupied.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        db.session.delete(lot)
        db.session.commit()
        flash(f'Successfully deleted "{lot.prime_location_name}".', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete the parking lot.', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/view_lot/<int:lot_id>')
@login_required
def view_parking_lot(lot_id):
    """View detailed information about a specific parking lot"""
    if current_user.role != 'admin':
        flash('Only administrators can view detailed parking lot information.', 'error')
        return redirect(url_for('user_dashboard'))
    
    lot = ParkingLot.query.get_or_404(lot_id)
    spots = ParkingSpot.query.filter_by(lot_id=lot_id).all()
    
    return render_template('view_lot.html', lot=lot, spots=spots)

@app.route('/user_dashboard')
@login_required
def user_dashboard():
    """User dashboard showing available parking and their history"""
    # Redirect admins to their own dashboard
    if current_user.role != 'user':
        return redirect(url_for('admin_dashboard'))
    
    # Get all available parking lots
    parking_lots = ParkingLot.query.all()
    
    # Check if user has an active parking reservation
    current_reservation = ParkingReservation.query.filter_by(
        user_id=current_user.id, 
        leaving_timestamp=None
    ).first()
    
    # Calculate how long they've been parked (if they are currently parked)
    current_duration = None
    if current_reservation:
        time_parked = datetime.utcnow() - current_reservation.parking_timestamp
        current_duration = time_parked.total_seconds() / 3600  # Convert to hours
    
    # Get their parking history
    history = ParkingReservation.query.filter_by(user_id=current_user.id).order_by(
        ParkingReservation.parking_timestamp.desc()
    ).limit(10).all()
    
    return render_template('user_dashboard.html', 
                         parking_lots=parking_lots,
                         current_reservation=current_reservation,
                         current_duration=current_duration,
                         history=history)

@app.route('/book_spot/<int:lot_id>')
@login_required
def book_spot(lot_id):
    """Book a parking spot for the current user"""
    # Only regular users can book spots
    if current_user.role != 'user':
        flash('Only regular users can book parking spots.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Make sure they don't already have a spot
    existing_reservation = ParkingReservation.query.filter_by(
        user_id=current_user.id, 
        leaving_timestamp=None
    ).first()
    
    if existing_reservation:
        flash('You already have an active parking reservation. Please release it first.', 'warning')
        return redirect(url_for('user_dashboard'))
    
    # Make sure the parking lot exists
    lot = ParkingLot.query.get(lot_id)
    if not lot:
        flash('Sorry, that parking lot could not be found.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Find the first available spot
    available_spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()
    
    if not available_spot:
        flash('Sorry, no spots are available in this parking lot right now.', 'error')
        return redirect(url_for('user_dashboard'))
    
    try:
        # Create the reservation
        reservation = ParkingReservation(
            spot_id=available_spot.id,
            user_id=current_user.id,
            parking_cost_per_unit_time=lot.price
        )
        
        # Mark the spot as occupied
        available_spot.status = 'O'  # O = Occupied
        
        db.session.add(reservation)
        db.session.commit()
        
        flash(f'Great! You\'ve booked spot {available_spot.spot_number} at {lot.prime_location_name}!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Booking error: {e}")  # For debugging
        flash('Something went wrong while booking your spot. Please try again.', 'error')
    
    return redirect(url_for('user_dashboard'))

@app.route('/release_spot')
@login_required
def release_spot():
    """Release the user's current parking spot"""
    if current_user.role != 'user':
        flash('Only regular users can release parking spots.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Find their current reservation
    reservation = ParkingReservation.query.filter_by(
        user_id=current_user.id, 
        leaving_timestamp=None
    ).first()
    
    if not reservation:
        flash('You don\'t have any active parking reservations to release.', 'warning')
        return redirect(url_for('user_dashboard'))
    
    try:
        # Mark when they left and calculate the total cost
        reservation.leaving_timestamp = datetime.utcnow()
        reservation.total_cost = reservation.calculate_total_cost()
        
        # Free up the parking spot
        spot = ParkingSpot.query.get(reservation.spot_id)
        if spot:
            spot.status = 'A'  # A = Available
        
        db.session.commit()
        
        spot_name = spot.spot_number if spot else 'your spot'
        flash(f'Successfully released {spot_name}. Total cost: ${reservation.total_cost:.2f}', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Release error: {e}")  # For debugging
        flash('Something went wrong while releasing your spot. Please try again.', 'error')
    
    return redirect(url_for('user_dashboard'))

@app.route('/admin/earnings')
@login_required
def admin_earnings():
    """Detailed earnings report for administrators"""
    if current_user.role != 'admin':
        flash('Only administrators can view earnings reports.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Get all completed reservations (where people have left)
    completed_reservations = ParkingReservation.query.filter(
        ParkingReservation.leaving_timestamp.isnot(None)
    ).order_by(ParkingReservation.leaving_timestamp.desc()).all()
    
    # Calculate total earnings
    total_earnings = sum(reservation.total_cost or 0 for reservation in completed_reservations)
    
    # Break down earnings by parking lot
    lot_earnings = {}
    for reservation in completed_reservations:
        lot_name = reservation.spot.lot.prime_location_name
        if lot_name not in lot_earnings:
            lot_earnings[lot_name] = 0
        lot_earnings[lot_name] += reservation.total_cost or 0
    
    return render_template('admin_earnings.html', 
                         completed_reservations=completed_reservations,
                         total_earnings=total_earnings,
                         lot_earnings=lot_earnings)

@app.route('/admin/users')
@login_required
def view_users():
    """View all registered users"""
    if current_user.role != 'admin':
        flash('Only administrators can view user information.', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Get all regular users (not admins) ordered by ID
    users = User.query.filter_by(role='user').order_by(User.id).all()
    return render_template('view_users.html', users=users)

# Run the app
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)