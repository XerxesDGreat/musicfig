from . import db

class Song(db.Model):
    __tablename__ = 'songs'
    id = db.Column(db.String(40), primary_key=True)
    image_url = db.Column(db.Text, nullable=True)
    artist = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(40),nullable=False)
    duration_ms = db.Column(db.Integer)

    def __repr__(self):
        return '<Song %s - %s>' % (self.artist, self.name)