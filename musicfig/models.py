import json

from . import db

class Song(db.Model):
    __tablename__ = "songs"
    id = db.Column(db.String(40), primary_key=True)
    image_url = db.Column(db.Text, nullable=True)
    artist = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(40),nullable=False)
    duration_ms = db.Column(db.Integer)

    def __repr__(self):
        return '<Song %s - %s>' % (self.artist, self.name)

class NFCTagModel(db.Model):
    __tablename__ = "nfc_tags"
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(40), nullable=True)
    description = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(20), nullable=True)
    attr = db.Column(db.Text, nullable=False)
    last_updated = db.Column(db.Integer)

    def get_attr_object(self):
        return json.loads(self.attr)