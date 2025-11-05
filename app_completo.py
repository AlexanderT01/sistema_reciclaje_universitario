from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from werkzeug.utils import secure_filename

#LIBRERIAS PARA EL REPORTE EN PDF 
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime
from flask import send_file 

# Importar models
from models import db, Usuario, MaterialReciclado
import os

app = Flask(__name__)

# CONFIGURACIÓN PARA PRODUCCIÓN
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave-temporal-desarrollo')

# Configuración de base de datos para producción
if os.environ.get('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reciclaje.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Inicializar la base de datos
db.init_app(app)

# Configuración para subida de archivos
# Configuración MEJORADA para subida de archivos
import tempfile
import os

# SOLO CAMBIA ESTA LÍNEA:
if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('DATABASE_URL'):
    # En producción (Railway) usar carpeta temporal
    app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'reciclaje_uploads')
    print(f"🌐 MODO PRODUCCIÓN: Uploads en {app.config['UPLOAD_FOLDER']}")
else:
    # En desarrollo (local) usar static/uploads
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    print(f"💻 MODO DESARROLLO: Uploads en {app.config['UPLOAD_FOLDER']}")

# Crear carpeta inmediatamente
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# MANTÉN ESTO IGUAL:
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# Ruta principal redirige a login
@app.route('/')
def index():
    return redirect(url_for('login'))

# Ruta de login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cedula = request.form['cedula']
        password = request.form['password']
        
        usuario = Usuario.query.filter_by(cedula=cedula).first()
        
        if usuario and check_password_hash(usuario.password, password):
            session['usuario_id'] = usuario.id
            session['usuario_nombre'] = usuario.nombre
            session['usuario_tipo'] = usuario.tipo
            session['usuario_facultad'] = usuario.facultad
            session['usuario_carrera'] = usuario.carrera
            session['usuario_departamento'] = usuario.departamento
            session['usuario_puntos'] = usuario.puntos
            
            # Solo dos tipos de redirección
            if usuario.tipo == 'administrador':
                return redirect(url_for('dashboard'))
            else:
                # Estudiantes, docentes y administrativos van al mismo dashboard de estudiante
                return redirect(url_for('estudiante_dashboard'))
        else:
            flash('Cédula o contraseña incorrectos', 'danger')
    
    return render_template('login.html')

#RUTA PARA GENERAR PDF 
@app.route('/generar-pdf-reporte')
def generar_pdf_reporte():
    try:
        # Obtener los datos para el reporte (usa las mismas consultas que en reportes)
        total_kg = db.session.query(func.sum(MaterialReciclado.peso)).filter(MaterialReciclado.estado == 'validado').scalar() or 0
        total_registros = MaterialReciclado.query.count()
        registros_validados = MaterialReciclado.query.filter_by(estado='validado').count()
        registros_pendientes = MaterialReciclado.query.filter_by(estado='pendiente').count()
        registros_rechazados = MaterialReciclado.query.filter_by(estado='rechazado').count()
        
        # Cálculos de impacto ambiental
        arboles_salvados = int(total_kg * 0.02)  # Ejemplo: 2 árboles por 100kg
        co2_evitado = int(total_kg * 2.5)  # Ejemplo: 2.5kg CO2 por kg reciclado
        
        # Distribución de materiales
        distribucion_materiales = db.session.query(
            MaterialReciclado.tipo_material,
            func.sum(MaterialReciclado.peso).label('total')
        ).filter(MaterialReciclado.estado == 'validado').group_by(MaterialReciclado.tipo_material).all()
        
        # Calcular porcentajes
        total_peso_valido = sum([item.total for item in distribucion_materiales])
        distribucion_con_porcentaje = []
        for material in distribucion_materiales:
            porcentaje = (material.total / total_peso_valido * 100) if total_peso_valido > 0 else 0
            distribucion_con_porcentaje.append({
                'tipo': material.tipo_material,
                'total': round(material.total, 2),
                'porcentaje': round(porcentaje, 1)
            })

        # Crear PDF en memoria
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30)
        elements = []
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#2E7D32'),
            spaceAfter=30,
            alignment=1  # Centrado
        )
        
        # Título
        title = Paragraph("REPORTE DE SOSTENIBILIDAD - SISTEMA DE RECICLAJE", title_style)
        elements.append(title)
        
        # Fecha de generación
        fecha = Paragraph(f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal'])
        elements.append(fecha)
        elements.append(Spacer(1, 20))
        
        # Métricas principales
        metrics_data = [
            ['MÉTRICA', 'VALOR'],
            ['Total material reciclado', f'{total_kg} kg'],
            ['Árboles salvados', f'{arboles_salvados}'],
            ['CO₂ evitado', f'{co2_evitado} kg'],
            ['Tipos de materiales', f'{len(distribucion_con_porcentaje)}']
        ]
        
        metrics_table = Table(metrics_data, colWidths=[3*inch, 2*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E7D32')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#E8F5E8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.gray)
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 20))
        
        # Estadísticas de validación
        validacion_data = [
            ['ESTADO', 'CANTIDAD', 'PORCENTAJE'],
            ['Validados', str(registros_validados), f'{registros_validados/total_registros*100:.1f}%' if total_registros > 0 else '0%'],
            ['Pendientes', str(registros_pendientes), f'{registros_pendientes/total_registros*100:.1f}%' if total_registros > 0 else '0%'],
            ['Rechazados', str(registros_rechazados), f'{registros_rechazados/total_registros*100:.1f}%' if total_registros > 0 else '0%'],
            ['TOTAL', str(total_registros), '100%']
        ]
        
        validacion_title = Paragraph("Estadísticas de Validación", styles['Heading2'])
        elements.append(validacion_title)
        elements.append(Spacer(1, 10))
        
        validacion_table = Table(validacion_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        validacion_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17A2B8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#343A40')),
            ('TEXTCOLOR', (0, 4), (-1, 4), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.gray)
        ]))
        elements.append(validacion_table)
        elements.append(Spacer(1, 20))
        
        # Distribución por material
        if distribucion_con_porcentaje:
            material_data = [['MATERIAL', 'PESO (kg)', 'PORCENTAJE']]
            for material in distribucion_con_porcentaje:
                material_data.append([
                    material['tipo'].title(),
                    str(material['total']),
                    f"{material['porcentaje']}%"
                ])
            
            material_title = Paragraph("Distribución por Tipo de Material", styles['Heading2'])
            elements.append(material_title)
            elements.append(Spacer(1, 10))
            
            material_table = Table(material_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
            material_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28A745')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.gray)
            ]))
            elements.append(material_table)
        
        # Nota final
        elements.append(Spacer(1, 30))
        nota = Paragraph(
            "<i>Reporte generado automáticamente por el Sistema de Reciclaje Universitario. "
            "Contribuyendo al ODS 12 - Producción y Consumo Responsables.</i>",
            styles['Italic']
        )
        elements.append(nota)
        
        # Generar PDF
        doc.build(elements)
        buffer.seek(0)
        
        # Devolver PDF como respuesta
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"reporte_reciclaje_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return f'Error al generar PDF: {str(e)}', 500


# RUTA DE REGISTRO
@app.route('/registro')
def registro():
    usuarios = Usuario.query.all()
    return render_template('registro.html', usuarios=usuarios)


# Registro de material para usuarios (formulario)
@app.route('/registrar-material-estudiante', methods=['GET','POST'])
def registrar_material_estudiante():
    print(f"DEBUG: Usuario intentando acceder - ID: {session.get('usuario_id')}, Tipo: {session.get('usuario_tipo')}")
    
    if 'usuario_id' not in session or session['usuario_tipo'] not in ['estudiante', 'docente', 'administrativo']:
        print(f"DEBUG: Redirigiendo al login - Usuario no autorizado")
        return redirect(url_for('login'))
    
    print(f"DEBUG: Acceso permitido, mostrando formulario")

    # Si es GET, mostrar el formulario
    if request.method == 'GET':
        return render_template('registro_material_estudiante.html')
    
    # Si es POST, procesar el formulario
    try:
        # SOLUCIÓN: Verificar y crear carpeta UPLOADS de forma segura
        upload_folder = app.config['UPLOAD_FOLDER']
        
        # Crear carpeta si no existe (con todos los directorios padres)
        os.makedirs(upload_folder, exist_ok=True)
        print(f"✅ Carpeta verificada/creada: {upload_folder}")
        
        # Verificar permisos de escritura
        if not os.access(upload_folder, os.W_OK):
            print(f"❌ Sin permisos de escritura en: {upload_folder}")
            flash('Error de configuración del sistema. Contacte al administrador.', 'danger')
            return render_template('registro_material_estudiante.html')
        
        if 'evidencia' not in request.files:
            flash('Debes subir una evidencia fotográfica', 'danger')
            return render_template('registro_material_estudiante.html')
        
        file = request.files['evidencia']
        
        # Si el usuario no selecciona archivo
        if file.filename == '':
            flash('No se seleccionó ningún archivo', 'danger')
            return render_template('registro_material_estudiante.html')
        
        if file and allowed_file(file.filename):
            # Guardar archivo
            filename = secure_filename(file.filename)
            # Hacer el nombre único
            unique_filename = f"{session['usuario_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            file_path = os.path.join(upload_folder, unique_filename)
            
            # VERIFICACIÓN EXTRA antes de guardar
            print(f"📁 Intentando guardar en: {file_path}")
            print(f"📁 Carpeta existe: {os.path.exists(upload_folder)}")
            print(f"📁 Permisos escritura: {os.access(upload_folder, os.W_OK)}")
            
            try:
                file.save(file_path)
                print(f"✅ Archivo guardado exitosamente: {unique_filename}")
            except Exception as save_error:
                print(f"❌ Error guardando archivo: {str(save_error)}")
                # FALLBACK: Guardar sin imagen pero permitir registro
                unique_filename = None
                flash('⚠️ Material registrado pero sin evidencia (error técnico temporal)', 'warning')
            
            # Obtener otros datos del formulario
            tipo_material = request.form['tipo_material']
            peso = float(request.form['peso'])
            punto_entrega = request.form['punto_entrega']
            
            # Calcular puntos (pero NO asignarlos todavía)
            puntos_por_kg = {'papel': 10, 'plástico': 15, 'vidrio': 12, 'metal': 20, 'orgánico': 5}
            puntos_ganados = int(peso * puntos_por_kg.get(tipo_material, 10))
            
            # Crear registro (con o sin evidencia)
            nuevo_registro = MaterialReciclado(
                usuario_id=session['usuario_id'],
                tipo_material=tipo_material,
                peso=peso,
                punto_entrega=punto_entrega,
                evidencia_img=unique_filename,  # Puede ser None si falló
                estado='pendiente',
                puntos_ganados=puntos_ganados
            )
            
            db.session.add(nuevo_registro)
            db.session.commit()
            
            flash('✅ Material registrado exitosamente! Espera la validación del administrador para recibir tus puntos.', 'success')
            return redirect(url_for('estudiante_dashboard'))
        else:
            flash('Formato de archivo no permitido. Use JPG, PNG o GIF', 'danger')
            return render_template('registro_material_estudiante.html')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error general al registrar: {str(e)}")
        flash(f'❌ Error al registrar: {str(e)}', 'danger')
        return render_template('registro_material_estudiante.html')


#from sqlalchemy import func

# Ruta del Dashboard Administrativo
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session or session['usuario_tipo'] != 'administrador':
        return redirect(url_for('login'))
    
    try:
        # Estadísticas generales
        total_usuarios = Usuario.query.filter(Usuario.tipo != 'administrador').count()  
        total_registros = MaterialReciclado.query.count()
        
        # Total de peso reciclado
        total_peso_result = db.session.query(func.sum(MaterialReciclado.peso)).scalar()
        total_peso = total_peso_result if total_peso_result else 0
        
        # Total de puntos
        total_puntos_result = db.session.query(func.sum(Usuario.puntos)).filter(Usuario.tipo != 'administrador').scalar()
        total_puntos = total_puntos_result if total_puntos_result else 0
        
        # Últimos 10 registros
        ultimos_registros = MaterialReciclado.query.options(db.joinedload(MaterialReciclado.usuario))\
            .order_by(MaterialReciclado.fecha_registro.desc()).limit(15).all()
        
        # Materiales por tipo
        materiales_por_tipo = db.session.query(
            MaterialReciclado.tipo_material,
            func.sum(MaterialReciclado.peso)
        ).group_by(MaterialReciclado.tipo_material).all()
        
        # Top 5 usuarios por puntos
        top_usuarios = Usuario.query.filter(Usuario.tipo != 'administrador')\
                                   .order_by(Usuario.puntos.desc())\
                                   .limit(5).all()
    
        return render_template('dashboard.html',
                             total_usuarios=total_usuarios,
                             total_registros=total_registros,
                             total_peso=round(total_peso, 2),
                             total_puntos=total_puntos,
                             ultimos_registros=ultimos_registros,
                             materiales_por_tipo=materiales_por_tipo,
                             top_usuarios=top_usuarios)  
    except Exception as e:
            return f'<h1>❌ Error en dashboard: {str(e)}</h1>'

# Ruta del Perfil de Usuario
@app.route('/perfil/<int:usuario_id>')
def perfil(usuario_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    # Verificar que el usuario solo pueda ver su propio perfil
    if session['usuario_tipo'] == 'estudiante' and session['usuario_id'] != usuario_id:
        flash('No tienes permisos para ver este perfil', 'danger')
        return redirect(url_for('estudiante_dashboard'))
    try:
        usuario = Usuario.query.get_or_404(usuario_id)
        
        # Sistema de niveles basado en puntos
        niveles = [
            (0, "Principiante"),
            (100, "Reciclador"),
            (300, "Reciclador Avanzado"), 
            (600, "Ecoguerrero"),
            (1000, "Héroe Ambiental")
        ]
        
        # Determinar nivel actual
        nivel_actual = 0
        nivel_nombre = "Principiante"
        proximo_nivel_puntos = 100
        
        for i, (puntos_min, nombre) in enumerate(niveles):
            if usuario.puntos >= puntos_min:
                nivel_actual = i
                nivel_nombre = nombre
                if i + 1 < len(niveles):
                    proximo_nivel_puntos = niveles[i + 1][0]
                else:
                    proximo_nivel_puntos = usuario.puntos + 100
        
        # Calcular porcentaje de progreso
        if nivel_actual + 1 < len(niveles):
            nivel_actual_puntos = niveles[nivel_actual][0]
            rango_puntos = proximo_nivel_puntos - nivel_actual_puntos
            puntos_en_rango = usuario.puntos - nivel_actual_puntos
            porcentaje_progreso = min(100, (puntos_en_rango / rango_puntos) * 100)
        else:
            porcentaje_progreso = 100
        
        # Beneficios disponibles
        beneficios = [
            {"nombre": "Certificado Ecológico", "descripcion": "Certificado digital de reconocimiento", "puntos_requeridos": 100},
            {"nombre": "Descuento 10% Cafetería", "descripcion": "Vale de descuento en cafetería universitaria", "puntos_requeridos": 200},
            {"nombre": "Kit Reciclaje Premium", "descripcion": "Bolsa ecológica y guantes reciclables", "puntos_requeridos": 400},
            {"nombre": "Reconocimiento Público", "descripcion": "Mención en redes sociales universitarias", "puntos_requeridos": 600},
            {"nombre": "Beca Ambiental", "descripcion": "Preferencia en becas de sostenibilidad", "puntos_requeridos": 1000}
        ]
        
        registros_pendientes = MaterialReciclado.query.filter_by(
            usuario_id=usuario_id, 
            estado='pendiente'
        ).count()

        registros_validados = MaterialReciclado.query.filter_by(
            usuario_id=usuario_id, 
            estado='validado'
        ).count()

        return render_template('perfil.html',
                             usuario=usuario,
                             nivel=nivel_actual + 1,
                             nivel_nombre=nivel_nombre,
                             proximo_nivel_puntos=proximo_nivel_puntos,
                             porcentaje_progreso=porcentaje_progreso,
                             registros_pendientes=registros_pendientes,
                             registros_validados=registros_validados,
                             beneficios=beneficios)
        
    except Exception as e:
        return f'<h1>❌ Error en perfil: {str(e)}</h1>'



# Ruta de Reportes Avanzados
@app.route('/reportes')
def reportes():
    if 'usuario_id' not in session or session['usuario_tipo'] != 'administrador':
        return redirect(url_for('login'))
    
    try:
        # Total de kg reciclados
        total_kg_result = db.session.query(func.sum(MaterialReciclado.peso))\
            .filter(MaterialReciclado.estado == 'validado')\
            .scalar()
        total_kg = total_kg_result if total_kg_result else 0
        
        # Cálculos básicos
        arboles_salvados = round(total_kg * 0.017) if total_kg > 0 else 0
        co2_evitado = round(total_kg * 1.5) if total_kg > 0 else 0
        km_equivalentes = round(co2_evitado / 0.12) if co2_evitado > 0 else 0
        energia_ahorrada = round(total_kg * 5) if total_kg > 0 else 0
        horas_bombillo = round(energia_ahorrada / 0.06) if energia_ahorrada > 0 else 0
        agua_ahorrada = round(total_kg * 100) if total_kg > 0 else 0
        duchas_equivalentes = round(agua_ahorrada / 60) if agua_ahorrada > 0 else 0
        
        # Distribución por materiales
        distribucion_materiales = []
        materiales_query = db.session.query(
            MaterialReciclado.tipo_material,
            func.sum(MaterialReciclado.peso).label('total')
        ).filter(MaterialReciclado.estado == 'validado')\
         .group_by(MaterialReciclado.tipo_material).all()
        
        for material, total in materiales_query:
            if total:
                porcentaje = round((total / total_kg) * 100, 1) if total_kg > 0 else 0
                distribucion_materiales.append({
                    'tipo': material,
                    'total': round(total, 1),
                    'porcentaje': porcentaje
                })
        
        # Puntos de entrega
        puntos_entrega = []
        puntos_query = db.session.query(
            MaterialReciclado.punto_entrega,
            func.count(MaterialReciclado.id).label('registros'),
            func.sum(MaterialReciclado.peso).label('total_kg')
        ).filter(MaterialReciclado.estado == 'validado')\
         .group_by(MaterialReciclado.punto_entrega).all()
        
        for punto, registros, total_kg_punto in puntos_query:
            puntos_entrega.append({
                'nombre': punto,
                'registros': registros,
                'total_kg': round(total_kg_punto or 0, 1)
            })
        
        # Métricas ODS 12
        tasa_reciclaje = min(100, round((total_kg / 500) * 100)) if total_kg > 0 else 0
        reduccion_huella = min(100, round((co2_evitado / 1000) * 100))
        total_estudiantes = Usuario.query.filter_by(tipo='estudiante').count()
        participacion = min(100, round((total_estudiantes / 50) * 100)) if total_estudiantes > 0 else 0
        
        # Estadísticas de estados para información
        total_registros = MaterialReciclado.query.count()
        registros_validados = MaterialReciclado.query.filter_by(estado='validado').count()
        registros_pendientes = MaterialReciclado.query.filter_by(estado='pendiente').count()
        registros_rechazados = MaterialReciclado.query.filter_by(estado='rechazado').count()
        
        return render_template('reportes.html',
                             total_kg=round(total_kg, 1),
                             arboles_salvados=arboles_salvados,
                             co2_evitado=co2_evitado,
                             km_equivalentes=km_equivalentes,
                             energia_ahorrada=energia_ahorrada,
                             horas_bombillo=horas_bombillo,
                             agua_ahorrada=agua_ahorrada,
                             duchas_equivalentes=duchas_equivalentes,
                             distribucion_materiales=distribucion_materiales,
                             puntos_entrega=puntos_entrega,
                             tasa_reciclaje=tasa_reciclaje,
                             reduccion_huella=reduccion_huella,
                             participacion=participacion,
                             # Nuevos datos para mostrar estadísticas
                             total_registros=total_registros,
                             registros_validados=registros_validados,
                             registros_pendientes=registros_pendientes,
                             registros_rechazados=registros_rechazados)
        
    except Exception as e:
        return f'<h1>❌ Error en reportes: {str(e)}</h1>'
    

# Dashboard para estudiantes
@app.route('/estudiante-dashboard')
def estudiante_dashboard():
    if 'usuario_id' not in session or session.get('usuario_tipo') not in ['estudiante', 'docente', 'administrativo']:
        flash('Debe iniciar sesión', 'warning')
        return redirect(url_for('login'))
    
    # Tu lógica actual del dashboard de estudiante aquí
    usuario = Usuario.query.get(session['usuario_id'])
    materiales = MaterialReciclado.query.filter_by(usuario_id=usuario.id).order_by(MaterialReciclado.fecha_registro.desc()).all()
    
    return render_template('estudiante_dashboard.html', 
                         usuario=usuario, 
                         materiales=materiales,
                         puntos=usuario.puntos)


# Ruta de registro de usuarios
@app.route('/registro-usuario', methods=['GET', 'POST'])
def registro_usuario():
    if request.method == 'POST':
        cedula = request.form['cedula']
        nombre = request.form['nombre']
        email = request.form['email']
        tipo_usuario = request.form['tipo_usuario']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'danger')
            return render_template('registro_usuario.html')
        
        if Usuario.query.filter_by(cedula=cedula).first():
            flash('Esta cédula ya está registrada', 'danger')
            return render_template('registro_usuario.html')
        
        if Usuario.query.filter_by(email=email).first():
            flash('Este email ya está registrado', 'danger')
            return render_template('registro_usuario.html')
        
        # Validar campos según el tipo de usuario
        facultad = ""
        carrera = ""
        departamento = ""
        
        if tipo_usuario == 'estudiante':
            facultad = request.form.get('facultad', '')
            carrera = request.form.get('carrera', '')
            if not facultad or not carrera:
                flash('Debes seleccionar facultad y carrera para estudiantes', 'danger')
                return render_template('registro_usuario.html')
                
        elif tipo_usuario == 'docente':
            facultad = request.form.get('facultad_docente', '')
            if not facultad:
                flash('Debes seleccionar una facultad para docentes', 'danger')
                return render_template('registro_usuario.html')
            departamento = f"Docente - {facultad}"
            
        elif tipo_usuario == 'administrativo':
            departamento = request.form.get('departamento_administrativo', '')
            if not departamento:
                flash('Debes ingresar un departamento para personal administrativo', 'danger')
                return render_template('registro_usuario.html')
            facultad = "Administración"
        
        # Crear usuario
        nuevo_usuario = Usuario(
            cedula=cedula,
            nombre=nombre,
            email=email,
            password=generate_password_hash(password),
            tipo=tipo_usuario,
            facultad=facultad,
            carrera=carrera,
            departamento=departamento
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        # Mensaje personalizado según el tipo
        if tipo_usuario == 'estudiante':
            mensaje = f'🎓 Registro exitoso como Estudiante de {carrera}'
        elif tipo_usuario == 'docente':
            mensaje = f'👨‍🏫 Registro exitoso como Docente de {facultad}'
        else:
            mensaje = f'💼 Registro exitoso como Personal Administrativo'
        
        flash(f'{mensaje}. Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))
    
    return render_template('registro_usuario.html')

# Cerrar sesión
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Validacion  ASIGNAR PUNTOS
@app.route('/validar-registro/<int:registro_id>', methods=['POST'])
def validar_registro(registro_id):
    if 'usuario_id' not in session or session['usuario_tipo'] != 'administrador':
        return {'success': False, 'error': 'No autorizado'}, 403
    
    try:
        registro = MaterialReciclado.query.get_or_404(registro_id)
        
        # Solo procesar si está pendiente
        if registro.estado != 'pendiente':
            return {'success': False, 'error': 'El registro ya fue procesado'}
        
        # Calcular puntos a asignar
        puntos_por_kg = {'papel': 10, 'plástico': 15, 'vidrio': 12, 'metal': 20, 'orgánico': 5}
        puntos_ganados = int(registro.peso * puntos_por_kg.get(registro.tipo_material, 10))
        
        # ASIGNAR PUNTOS al usuario
        usuario = Usuario.query.get(registro.usuario_id)
        usuario.puntos += puntos_ganados
        
        # Cambiar estado a VALIDADO
        registro.estado = 'validado'
        
        db.session.commit()
        
        return {
            'success': True, 
            'puntos_ganados': puntos_ganados,
            'usuario_nombre': usuario.nombre
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Rechazar registro - NO asignar puntos
@app.route('/rechazar-registro/<int:registro_id>', methods=['POST'])
def rechazar_registro(registro_id):
    if 'usuario_id' not in session or session['usuario_tipo'] != 'administrador':
        return {'success': False, 'error': 'No autorizado'}, 403
    
    try:
        data = request.get_json()
        motivo = data.get('motivo', 'Sin motivo especificado')
        
        registro = MaterialReciclado.query.get_or_404(registro_id)
        
        # Solo procesar si está pendiente
        if registro.estado != 'pendiente':
            return {'success': False, 'error': 'El registro ya fue procesado'}
        
        #NO asignar puntos, solo cambiar estado
        registro.estado = 'rechazado'
        
        db.session.commit()
        
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# Crear tablas si no existen
with app.app_context():
    db.create_all()
    
    print("🔧 INICIANDO CREACIÓN DE DATOS...")
    
    # ELIMINAR datos existentes para empezar fresco
    try:
        MaterialReciclado.query.delete()
        Usuario.query.delete()
        db.session.commit()
        print("✅ Tablas limpiadas")
    except:
        db.session.rollback()
        print("⚠️ No se pudieron limpiar tablas (probablemente ya estaban vacías)")
    
    # CREAR ADMINISTRADOR
    if not Usuario.query.filter_by(cedula='admin123').first():
        admin = Usuario(
            cedula='admin123',
            nombre='Administrador Principal',
            email='admin@universidad.edu',
            password=generate_password_hash('admin123'),
            tipo='administrador',
            facultad='Sistema',
            departamento='TI'
        )
        db.session.add(admin)
        print("✅ Administrador creado")
    
    # CREAR USUARIOS DE PRUEBA
    usuarios_prueba = [
        {
            'cedula': '20240001',
            'nombre': 'Ana García',
            'email': 'ana@estudiante.edu',
            'password': 'estudiante123',
            'tipo': 'estudiante',
            'facultad': 'Ingeniería',
            'carrera': 'Sistemas',
            'puntos': 85
        },
        {
            'cedula': '20240002', 
            'nombre': 'Carlos Rodríguez',
            'email': 'carlos@estudiante.edu',
            'password': 'estudiante123',
            'tipo': 'estudiante',
            'facultad': 'Ciencias',
            'carrera': 'Biología',
            'puntos': 120
        },
        {
            'cedula': '1001001',
            'nombre': 'Dra. María López',
            'email': 'maria@docente.edu',
            'password': 'docente123', 
            'tipo': 'docente',
            'facultad': 'Medicina',
            'departamento': 'Anatomía'
        }
    ]
    
    for user_data in usuarios_prueba:
        if not Usuario.query.filter_by(cedula=user_data['cedula']).first():
            usuario = Usuario(
                cedula=user_data['cedula'],
                nombre=user_data['nombre'],
                email=user_data['email'],
                password=generate_password_hash(user_data['password']),
                tipo=user_data['tipo'],
                facultad=user_data['facultad'],
                puntos=user_data.get('puntos', 0)
            )
            if user_data['tipo'] == 'estudiante':
                usuario.carrera = user_data.get('carrera', '')
            else:
                usuario.departamento = user_data.get('departamento', '')
            
            db.session.add(usuario)
            print(f"✅ Usuario creado: {user_data['nombre']}")
    
    # CREAR MATERIALES DE PRUEBA
    materiales_prueba = [
        {
            'usuario_id': 2,  # Ana García
            'tipo_material': 'plástico',
            'peso': 2.5,
            'punto_entrega': 'Edificio de Ingeniería',
            'estado': 'validado',
            'puntos_ganados': 37
        },
        {
            'usuario_id': 2,
            'tipo_material': 'papel',
            'peso': 1.0,
            'punto_entrega': 'Biblioteca Central', 
            'estado': 'pendiente',
            'puntos_ganados': 10
        },
        {
            'usuario_id': 3,  # Carlos Rodríguez
            'tipo_material': 'vidrio',
            'peso': 3.0,
            'punto_entrega': 'Laboratorio de Ciencias',
            'estado': 'validado',
            'puntos_ganados': 36
        },
        {
            'usuario_id': 4,  # Dra. María López
            'tipo_material': 'metal',
            'peso': 1.5,
            'punto_entrega': 'Hospital Universitario',
            'estado': 'rechazado',
            'puntos_ganados': 30
        }
    ]
    
    for material_data in materiales_prueba:
        material = MaterialReciclado(**material_data)
        db.session.add(material)
        print(f"✅ Material creado: {material_data['tipo_material']} - {material_data['peso']}kg")
    
    # GUARDAR TODO
    try:
        db.session.commit()
        print("🎉 TODOS LOS DATOS DE PRUEBA CREADOS EXITOSAMENTE!")
        print("👑 Administrador: admin123 / admin123")
        print("🎓 Estudiante 1: 20240001 / estudiante123")
        print("🎓 Estudiante 2: 20240002 / estudiante123") 
        print("👨‍🏫 Docente: 1001001 / docente123")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al guardar datos: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)