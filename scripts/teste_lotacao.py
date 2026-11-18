from core.extensions import db

class Lotacao(db.Model):
    __tablename__ = 'lotacoes'

    id_lotacao = db.Column(db.Integer, primary_key=True)
    lotacao = db.Column(db.String(200), nullable=True)
    area = db.Column(db.String(200), nullable=True)
    coordenadoria = db.Column(db.String(200), nullable=True)
