from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

# Initialize our database
db = SQLAlchemy()

class User(db.Model, UserMixin):
    """
    Represents a user in our parking system.
    Can be either a regular user or an admin.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # This will be hashed
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user' or 'admin'
    registration_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

class ParkingLot(db.Model):
    """
    Represents a parking lot location with multiple parking spots.
    Contains pricing and location information.
    """
    id = db.Column(db.Integer, primary_key=True)
    prime_location_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)  # Price per hour
    address = db.Column(db.Text, nullable=False)
    pin_code = db.Column(db.String(10), nullable=False)
    maximum_number_of_spots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship - this lot has many spots
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ParkingLot {self.prime_location_name}>'
    
    @property
    def available_spots_count(self):
        """Count how many spots are currently available"""
        return len([spot for spot in self.spots if spot.status == 'A'])
    
    @property
    def occupied_spots_count(self):
        """Count how many spots are currently occupied"""
        return len([spot for spot in self.spots if spot.status == 'O'])

class ParkingSpot(db.Model):
    """
    Represents an individual parking spot within a parking lot.
    Can be either available or occupied.
    """
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    spot_number = db.Column(db.String(20), nullable=False)  # Like "MAL-001"
    status = db.Column(db.String(1), default='A')  # 'A' = Available, 'O' = Occupied
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship - this spot can have many reservations over time
    reservations = db.relationship('ParkingReservation', backref='spot', lazy=True)

    def __repr__(self):
        return f'<ParkingSpot {self.spot_number}>'
    
    @property
    def current_reservation(self):
        """Get the current active reservation for this spot (if any)"""
        return ParkingReservation.query.filter_by(
            spot_id=self.id, 
            leaving_timestamp=None
        ).first()

class ParkingReservation(db.Model):
    """
    Represents a parking reservation - when someone parks and when they leave.
    Tracks timing and calculates costs.
    """
    id = db.Column(db.Integer, primary_key=True)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parking_timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # When they parked
    leaving_timestamp = db.Column(db.DateTime, nullable=True)  # When they left (null if still parked)
    parking_cost_per_unit_time = db.Column(db.Float, nullable=False)  # Rate per hour
    total_cost = db.Column(db.Float, nullable=True)  # Final cost (calculated when they leave)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

    def __repr__(self):
        return f'<ParkingReservation {self.id}>'
    
    @property
    def duration_hours(self):
        """Calculate how long this parking session lasted (or is lasting)"""
        if self.leaving_timestamp:
            # They've left - calculate the actual duration
            duration = self.leaving_timestamp - self.parking_timestamp
            return duration.total_seconds() / 3600
        else:
            # They're still parked - calculate current duration
            duration = datetime.utcnow() - self.parking_timestamp
            return duration.total_seconds() / 3600
    
    def calculate_total_cost(self):
        """Calculate the total cost based on how long they parked"""
        if self.leaving_timestamp:
            hours_parked = self.duration_hours
            return round(hours_parked * self.parking_cost_per_unit_time, 2)
        return 0  # Can't calculate cost if they haven't left yet