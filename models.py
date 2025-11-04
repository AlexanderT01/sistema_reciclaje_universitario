# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), default='estudiante')
    facultad = db.Column(db.String(100))
    carrera = db.Column(db.String(100))
    departamento = db.Column(db.String(100))
    puntos = db.Column(db.Integer, default=0)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Usuario {self.nombre}>'

class MaterialReciclado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    tipo_material = db.Column(db.String(50), nullable=False)
    peso = db.Column(db.Float, nullable=False)
    punto_entrega = db.Column(db.String(100), nullable=False)
    evidencia_img = db.Column(db.String(200))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default='pendiente')
    puntos_ganados = db.Column(db.Integer, default=0)

    usuario = db.relationship('Usuario', backref=db.backref('registros', lazy=True))

    def __repr__(self):
        return f'<MaterialReciclado {self.tipo_material} - {self.peso}kg>'