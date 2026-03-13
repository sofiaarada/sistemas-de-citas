from __future__ import annotations

from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, url_for
from mysql.connector import Error

from config import settings
from database import execute, fetch_all, fetch_one

APPOINTMENT_TYPES = (
    "MEDICINA_GENERAL",
    "ODONTOLOGIA",
    "PEDIATRIA",
    "GINECOLOGIA",
    "LABORATORIO",
)
MODALITIES = ("PRESENCIAL", "VIRTUAL")
STATUS_OPTIONS = ("PROGRAMADA", "ATENDIDA", "CANCELADA")


def _safe_strip(value: str | None) -> str:
    return (value or "").strip()


def _is_future_slot(fecha: str, hora: str) -> bool:
    appointment_datetime = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    return appointment_datetime > datetime.now()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key

    @app.route("/")
    def index():
        metrics = {
            "pacientes": 0,
            "citas_programadas": 0,
            "citas_hoy": 0,
        }
        citas_proximas = []

        try:
            metrics_query = """
            SELECT
                (SELECT COUNT(*) FROM pacientes) AS pacientes,
                (SELECT COUNT(*) FROM citas WHERE estado = 'PROGRAMADA') AS citas_programadas,
                (SELECT COUNT(*) FROM citas WHERE fecha = CURDATE() AND estado = 'PROGRAMADA') AS citas_hoy
            """
            metrics = fetch_one(metrics_query, dictionary=True) or metrics

            citas_query = """
            SELECT
                c.id,
                p.documento,
                CONCAT(p.nombres, ' ', p.apellidos) AS paciente,
                m.nombre AS medico,
                m.especialidad,
                c.tipo_cita,
                DATE_FORMAT(c.fecha, '%Y-%m-%d') AS fecha,
                DATE_FORMAT(c.hora, '%H:%i') AS hora,
                c.modalidad,
                c.estado
            FROM citas c
            JOIN pacientes p ON p.id = c.paciente_id
            JOIN medicos m ON m.id = c.medico_id
            WHERE c.estado = 'PROGRAMADA'
            ORDER BY c.fecha ASC, c.hora ASC
            LIMIT 8
            """
            citas_proximas = fetch_all(citas_query, dictionary=True)
        except Error:
            flash("No fue posible cargar el tablero. Verifica la conexion a MySQL.", "danger")

        return render_template("index.html", metrics=metrics, citas_proximas=citas_proximas)

    @app.route("/registrar", methods=["GET", "POST"])
    def registrar():
        form_data = {
            "documento": "",
            "nombres": "",
            "apellidos": "",
            "fecha_nacimiento": "",
            "telefono": "",
            "email": "",
            "eps": "",
        }

        if request.method == "POST":
            form_data = {
                "documento": _safe_strip(request.form.get("documento")),
                "nombres": _safe_strip(request.form.get("nombres")),
                "apellidos": _safe_strip(request.form.get("apellidos")),
                "fecha_nacimiento": _safe_strip(request.form.get("fecha_nacimiento")),
                "telefono": _safe_strip(request.form.get("telefono")),
                "email": _safe_strip(request.form.get("email")),
                "eps": _safe_strip(request.form.get("eps")),
            }

            errors = []

            if not form_data["documento"].isdigit() or len(form_data["documento"]) < 6:
                errors.append("El documento debe ser numerico y tener minimo 6 digitos.")

            if len(form_data["nombres"]) < 2:
                errors.append("Nombres invalido.")

            if len(form_data["apellidos"]) < 2:
                errors.append("Apellidos invalido.")

            if not form_data["telefono"].isdigit() or len(form_data["telefono"]) < 7:
                errors.append("Telefono invalido.")

            if "@" not in form_data["email"] or "." not in form_data["email"]:
                errors.append("Correo invalido.")

            if not form_data["eps"]:
                errors.append("Debes indicar la EPS.")

            try:
                if not form_data["fecha_nacimiento"]:
                    errors.append("La fecha de nacimiento es obligatoria.")
                else:
                    born_date = datetime.strptime(form_data["fecha_nacimiento"], "%Y-%m-%d").date()
                    if born_date >= datetime.now().date():
                        errors.append("La fecha de nacimiento no puede ser hoy ni futura.")
            except ValueError:
                errors.append("Fecha de nacimiento invalida.")

            if errors:
                for error in errors:
                    flash(error, "warning")
                return render_template("registrar_paciente.html", form_data=form_data)

            try:
                insert_query = """
                INSERT INTO pacientes (
                    documento,
                    nombres,
                    apellidos,
                    fecha_nacimiento,
                    telefono,
                    email,
                    eps
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                execute(
                    insert_query,
                    (
                        form_data["documento"],
                        form_data["nombres"],
                        form_data["apellidos"],
                        form_data["fecha_nacimiento"],
                        form_data["telefono"],
                        form_data["email"],
                        form_data["eps"],
                    ),
                )
            except Error as exc:
                if exc.errno == 1062:
                    flash("Ese documento ya se encuentra registrado.", "warning")
                else:
                    flash("No se pudo registrar el paciente.", "danger")
                return render_template("registrar_paciente.html", form_data=form_data)

            flash("Paciente registrado correctamente.", "success")
            return redirect(url_for("registrar"))

        return render_template("registrar_paciente.html", form_data=form_data)

    @app.route("/reservar", methods=["GET", "POST"])
    def reservar():
        form_data = {
            "documento": "",
            "medico_id": "",
            "tipo_cita": APPOINTMENT_TYPES[0],
            "fecha": "",
            "hora": "",
            "modalidad": MODALITIES[0],
            "sede": "",
            "observaciones": "",
        }

        medicos = []
        try:
            medicos = fetch_all(
                "SELECT id, nombre, especialidad, consultorio FROM medicos WHERE activo = 1 ORDER BY nombre",
                dictionary=True,
            )
        except Error:
            flash("No fue posible cargar el listado de medicos.", "danger")

        if request.method == "POST":
            form_data = {
                "documento": _safe_strip(request.form.get("documento")),
                "medico_id": _safe_strip(request.form.get("medico_id")),
                "tipo_cita": _safe_strip(request.form.get("tipo_cita")),
                "fecha": _safe_strip(request.form.get("fecha")),
                "hora": _safe_strip(request.form.get("hora")),
                "modalidad": _safe_strip(request.form.get("modalidad")),
                "sede": _safe_strip(request.form.get("sede")),
                "observaciones": _safe_strip(request.form.get("observaciones")),
            }

            errors = []

            if not form_data["documento"].isdigit():
                errors.append("Documento invalido.")

            if not form_data["medico_id"].isdigit():
                errors.append("Debes elegir un medico valido.")

            if form_data["tipo_cita"] not in APPOINTMENT_TYPES:
                errors.append("Tipo de cita invalido.")

            if form_data["modalidad"] not in MODALITIES:
                errors.append("Modalidad invalida.")

            if not form_data["sede"]:
                errors.append("Debes indicar la sede de atencion.")

            try:
                if not _is_future_slot(form_data["fecha"], form_data["hora"]):
                    errors.append("La cita debe quedar en una fecha y hora futura.")
            except ValueError:
                errors.append("Fecha u hora invalidas.")

            paciente = None
            if not errors:
                try:
                    paciente = fetch_one(
                        "SELECT id FROM pacientes WHERE documento = %s",
                        (form_data["documento"],),
                        dictionary=True,
                    )
                except Error:
                    errors.append("Error consultando el paciente en la base de datos.")

            if not errors and not paciente:
                errors.append("El paciente no existe. Debes registrarlo primero.")

            if errors:
                for error in errors:
                    flash(error, "warning")
                return render_template(
                    "reservar_cita.html",
                    medicos=medicos,
                    appointment_types=APPOINTMENT_TYPES,
                    modalities=MODALITIES,
                    form_data=form_data,
                )

            try:
                insert_query = """
                INSERT INTO citas (
                    paciente_id,
                    medico_id,
                    tipo_cita,
                    fecha,
                    hora,
                    modalidad,
                    sede,
                    observaciones,
                    estado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PROGRAMADA')
                """
                execute(
                    insert_query,
                    (
                        paciente["id"],
                        int(form_data["medico_id"]),
                        form_data["tipo_cita"],
                        form_data["fecha"],
                        form_data["hora"],
                        form_data["modalidad"],
                        form_data["sede"],
                        form_data["observaciones"] or None,
                    ),
                )
            except Error as exc:
                if exc.errno == 1062:
                    flash("Ese medico ya tiene una cita asignada en ese horario.", "warning")
                else:
                    flash("No fue posible reservar la cita.", "danger")
                return render_template(
                    "reservar_cita.html",
                    medicos=medicos,
                    appointment_types=APPOINTMENT_TYPES,
                    modalities=MODALITIES,
                    form_data=form_data,
                )

            flash("Cita reservada correctamente.", "success")
            return redirect(url_for("reservar"))

        return render_template(
            "reservar_cita.html",
            medicos=medicos,
            appointment_types=APPOINTMENT_TYPES,
            modalities=MODALITIES,
            form_data=form_data,
        )

    @app.route("/consultar", methods=["GET", "POST"])
    def consultar():
        documento = _safe_strip(request.values.get("documento"))
        paciente = None
        citas = []

        if documento:
            try:
                paciente_query = """
                SELECT
                    id,
                    documento,
                    CONCAT(nombres, ' ', apellidos) AS paciente,
                    telefono,
                    email,
                    eps
                FROM pacientes
                WHERE documento = %s
                """
                paciente = fetch_one(paciente_query, (documento,), dictionary=True)

                if paciente:
                    citas_query = """
                    SELECT
                        c.id,
                        c.tipo_cita,
                        DATE_FORMAT(c.fecha, '%Y-%m-%d') AS fecha,
                        DATE_FORMAT(c.hora, '%H:%i') AS hora,
                        c.modalidad,
                        c.sede,
                        c.estado,
                        m.nombre AS medico,
                        m.especialidad,
                        c.observaciones
                    FROM citas c
                    JOIN medicos m ON m.id = c.medico_id
                    WHERE c.paciente_id = %s
                    ORDER BY c.fecha DESC, c.hora DESC
                    """
                    citas = fetch_all(citas_query, (paciente["id"],), dictionary=True)
                elif request.method == "POST":
                    flash("No existe un paciente con ese documento.", "warning")
            except Error:
                flash("No fue posible consultar la informacion solicitada.", "danger")
        elif request.method == "POST":
            flash("Ingresa un documento para consultar.", "warning")

        return render_template(
            "consultar_cita.html",
            documento=documento,
            paciente=paciente,
            citas=citas,
        )

    @app.route("/actualizar/<int:cita_id>")
    def actualizar_by_id(cita_id: int):
        return redirect(url_for("actualizar", cita_id=cita_id))

    @app.route("/actualizar", methods=["GET", "POST"])
    def actualizar():
        if request.method == "POST":
            cita_id = request.form.get("cita_id", type=int)
            documento = _safe_strip(request.form.get("documento"))
            medico_id = _safe_strip(request.form.get("medico_id"))
            tipo_cita = _safe_strip(request.form.get("tipo_cita"))
            fecha = _safe_strip(request.form.get("fecha"))
            hora = _safe_strip(request.form.get("hora"))
            modalidad = _safe_strip(request.form.get("modalidad"))
            sede = _safe_strip(request.form.get("sede"))
            estado = _safe_strip(request.form.get("estado"))
            observaciones = _safe_strip(request.form.get("observaciones"))

            errors = []

            if not cita_id:
                errors.append("La cita enviada no es valida.")

            if not medico_id.isdigit():
                errors.append("Medico invalido.")

            if tipo_cita not in APPOINTMENT_TYPES:
                errors.append("Tipo de cita invalido.")

            if modalidad not in MODALITIES:
                errors.append("Modalidad invalida.")

            if estado not in STATUS_OPTIONS:
                errors.append("Estado invalido.")

            if not sede:
                errors.append("La sede no puede quedar vacia.")

            if estado == "PROGRAMADA":
                try:
                    if not _is_future_slot(fecha, hora):
                        errors.append("Una cita programada debe estar en una fecha y hora futura.")
                except ValueError:
                    errors.append("Fecha u hora invalidas.")

            if errors:
                for error in errors:
                    flash(error, "warning")
                return redirect(url_for("actualizar", cita_id=cita_id))

            try:
                update_query = """
                UPDATE citas
                SET
                    medico_id = %s,
                    tipo_cita = %s,
                    fecha = %s,
                    hora = %s,
                    modalidad = %s,
                    sede = %s,
                    estado = %s,
                    observaciones = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
                rows_updated = execute(
                    update_query,
                    (
                        int(medico_id),
                        tipo_cita,
                        fecha,
                        hora,
                        modalidad,
                        sede,
                        estado,
                        observaciones or None,
                        cita_id,
                    ),
                )

                if rows_updated == 0:
                    flash("No se encontro la cita para actualizar.", "warning")
                    return redirect(url_for("consultar", documento=documento))
            except Error as exc:
                if exc.errno == 1062:
                    flash("Conflicto de horario: el medico ya tiene una cita en ese espacio.", "warning")
                else:
                    flash("No fue posible actualizar la cita.", "danger")
                return redirect(url_for("actualizar", cita_id=cita_id))

            flash("Cita actualizada correctamente.", "success")
            if documento:
                return redirect(url_for("consultar", documento=documento))
            return redirect(url_for("index"))

        cita_id = request.args.get("cita_id", type=int)
        if not cita_id:
            flash("Debes elegir una cita desde la consulta para poder actualizar.", "warning")
            return redirect(url_for("consultar"))

        try:
            cita_query = """
            SELECT
                c.id,
                p.documento,
                CONCAT(p.nombres, ' ', p.apellidos) AS paciente,
                c.medico_id,
                c.tipo_cita,
                DATE_FORMAT(c.fecha, '%Y-%m-%d') AS fecha,
                DATE_FORMAT(c.hora, '%H:%i') AS hora,
                c.modalidad,
                c.sede,
                c.estado,
                c.observaciones
            FROM citas c
            JOIN pacientes p ON p.id = c.paciente_id
            WHERE c.id = %s
            """
            cita = fetch_one(cita_query, (cita_id,), dictionary=True)

            if not cita:
                flash("La cita solicitada no existe.", "warning")
                return redirect(url_for("consultar"))

            medicos = fetch_all(
                "SELECT id, nombre, especialidad, consultorio FROM medicos WHERE activo = 1 ORDER BY nombre",
                dictionary=True,
            )
        except Error:
            flash("No fue posible cargar la cita para actualizar.", "danger")
            return redirect(url_for("consultar"))

        return render_template(
            "actualizar_cita.html",
            cita=cita,
            medicos=medicos,
            appointment_types=APPOINTMENT_TYPES,
            modalities=MODALITIES,
            status_options=STATUS_OPTIONS,
        )

    @app.post("/citas/<int:cita_id>/cancelar")
    def cancelar(cita_id: int):
        documento = _safe_strip(request.form.get("documento"))

        try:
            rows_updated = execute(
                """
                UPDATE citas
                SET estado = 'CANCELADA', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND estado <> 'CANCELADA'
                """,
                (cita_id,),
            )

            if rows_updated == 0:
                flash("La cita ya estaba cancelada o no existe.", "warning")
            else:
                flash("Cita cancelada correctamente.", "success")
        except Error:
            flash("No fue posible cancelar la cita.", "danger")

        if documento:
            return redirect(url_for("consultar", documento=documento))
        return redirect(url_for("consultar"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
