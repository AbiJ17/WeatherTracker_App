from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    country_code = db.Column(db.String(10))

    __table_args__ = (db.UniqueConstraint('city', 'country_code', name='_city_country_uc'),)
