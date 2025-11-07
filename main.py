import os
import re
import pdfplumber
from pathlib import Path
from datetime import datetime
from docxtpl import DocxTemplate
from dotenv import load_dotenv
from docxtpl import RichText
import google.generativeai as genai



# === CONFIGURACIÓN ===
BASE_DIR = Path(__file__).parent
CITACIONES_DIR = BASE_DIR / "Citaciones"
ACTAS_DIR = BASE_DIR / "ActasGeneradas"
PLANTILLA_ACTA = BASE_DIR / "plantillas_acta2.docx"
ENV_PATH = BASE_DIR / ".env"

# === Cargar clave API ===
load_dotenv(ENV_PATH)
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("⚠️ GEMINI_API_KEY no encontrada en .env. Se usarán preguntas genéricas.")


# === LECTURA DE PDF ===
def leer_texto_pdf(path: Path) -> str:
    """Extrae el texto plano de todas las páginas del PDF."""
    texto = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                texto += page.extract_text() + "\n"
        texto = re.sub(r"\s+", " ", texto)
        return texto.strip()
    except Exception as e:
        print(f"❌ Error leyendo PDF {path.name}: {e}")
        return ""

# === EXTRACCIÓN COMPLETA DE ARTÍCULOS ===
def extraer_articulos_completos(texto: str) -> str:
    """
    Extrae el bloque de artículos tal como aparece en la citación.
    Toma el texto entre la frase inicial (después de 'Falta Grave...') y la frase final ('Se le informa al trabajador...').
    """
    # Normalizar saltos de línea y espacios
    texto = texto.replace("\r", " ").replace("\n", " ").strip()

    # Definir delimitadores
    inicio_patron = re.search(
        r"Las\s+conductas\s+que\s+se\s+le\s+imputan\s+se\s+han\s+calificado\s+provisionalmente\s+como\s+Falta\s+Grave[\s\S]*?empresa[:]*",
        texto,
        flags=re.IGNORECASE
    )
    fin_patron = re.search(
        r"Se\s+le\s+informa\s+al\s+trabajador\s+sobre\s+la\s+oportunidad\s+de\s+presentar",
        texto,
        flags=re.IGNORECASE
    )

    if not inicio_patron or not fin_patron:
        return "No se encontraron los artículos en la citación."

    # Extraer el bloque intermedio
    articulos_texto = texto[inicio_patron.end():fin_patron.start()].strip()

    # Limpieza básica
    articulos_texto = re.sub(r"\s{2,}", " ", articulos_texto)  # quita espacios dobles
    articulos_texto = re.sub(r"(Artículo\s+\d+)", r"\n\1", articulos_texto, flags=re.IGNORECASE)  # salto antes de cada Artículo
    articulos_texto = articulos_texto.strip()

    return articulos_texto if len(articulos_texto) > 20 else "No se encontraron artículos válidos."

# === EXTRACCIÓN DE DATOS DE LA CITACIÓN ===

def extraer_datos_citacion(texto: str) -> dict:
    """Extrae los datos principales de una citación en PDF según el formato de AGP."""
    
    # Normalizar texto
    t = texto.replace("\r", " ").replace("\n", " ").strip()

    # === Nombre del colaborador ===
    m = re.search(r"Señor\s*\(a\)\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s]+)", t)
    nombre = m.group(1).strip().title() if m else "No encontrado"

    # === Cédula (línea justo debajo del nombre) ===
    # Buscamos el nombre y tomamos hasta 40 caracteres después para capturar número
    m = re.search(
        r"Señor\s*\(a\)\s*[:\-]?\s*[A-ZÁÉÍÓÚÑ\s]+\s+([0-9]{5,15})",
        t,
        re.IGNORECASE,
    )
    cedula = m.group(1).strip() if m else "No encontrada"

    # === Fecha de la citación ===
    # Admite "de 2025" o "2025", con o sin puntos en am/pm
    m = re.search(
        r"el\s+d[ií]a\s+(\d{1,2}\s+de\s+[a-zA-Zñ]+\s+(?:de\s+)?\d{4}\s+a\s+las\s+[0-9:.]+\s*(?:a\.?m\.?|p\.?m\.?)?)",
        t,
        re.IGNORECASE,
    )
    fecha_citacion = m.group(1).strip() if m else "No encontrada"

    # === Fecha del hecho ===
    m = re.search(r"Cometidos\s+el\s+d[ií]a[:\s]+([0-9\-\/]+)", t, re.IGNORECASE)
    fecha_hecho = m.group(1).strip() if m else "No encontrada"

    # === Detalle del caso ===
    m = re.search(
        r"compañ[ií]a[:\-]?\s*(.+?)Cometidos\s+el\s+d[ií]a",
        t,
        re.IGNORECASE | re.DOTALL,
    )
    detalle = m.group(1).strip() if m else "No se encontró detalle"

    # === Tipo de Falta (detiene al encontrar punto, coma o frase siguiente) ===
    m = re.search(
        r"Tipo\s+de\s+Falta[:\-]?\s*([A-Za-zÁÉÍÓÚÑ\s]+?)(?:\.|,|las\s+conductas|según|$)",
        t,
        re.IGNORECASE,
    )
    tipo_falta = m.group(1).strip().title() if m else "No encontrada"

    # === Artículos citados ===
    articulos = extraer_articulos_completos(texto)

    return {
        "nombre": nombre,
        "cedula": cedula,
        "fecha_citacion": fecha_citacion,
        "fecha_hecho": fecha_hecho,
        "detalle": detalle,
        "tipo_falta": tipo_falta,
        "articulos": articulos,
    }




# === PREGUNTAS BASE POR TIPO DE  ===
def preguntas_base_por_tipo(tipo: str) -> list:
    """Devuelve las preguntas base según el tipo de falta detectado."""
    tipo = tipo.strip().lower()
    if "procedimiento" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Sabe usted que debe actuar con diligencia y cuidado para asegurar la calidad y eficiencia en su trabajo, según el artículo 54 del Reglamento Interno?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente diligencia?"
        ]
    elif "ausencia" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Por qué no asistió a trabajar los días mencionados?",
            "¿Tiene algún soporte que justifique sus ausencias?",
            "¿Sabe usted que se les prohíbe a los trabajadores faltar al turno o jornada de trabajo sin justa causa de impedimento o sin permiso de la Empresa?",
            "¿Sabe usted que es una falta grave la falta parcial o total en la jornada de la mañana o de la tarde para el personal administrativo, o en el turno correspondiente para el personal operativo, sin excusa suficiente?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente?"
        ]
    elif "epp" in tipo or "protección" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Usted se encontraba haciendo caso omiso del uso de EPPS?",
            "¿Por qué motivo no estaba usando los EPPS?",
            "¿Sabe usted que es prohibido “Hacer caso omiso en el uso de los elementos de protección personal y ejecutar cualquier acto inseguro que ponga en peligro su seguridad”?",
            "¿Usted es consciente que pudo tener una afectación más grave ya que se trabaja en AGP con vidrio y maquinaria y el uso de EPPs es esencial para desarrollar las labores en AGP?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente?"
        ]
    elif "celular" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Confirme o niegue si tenía permiso para utilizar el celular en el área de trabajo?",
            "¿En ocasiones anteriores ha hecho uso del celular en su puesto de trabajo?",
            "¿Usted conoce la política de celulares estipulada por la compañía?",
            "De acuerdo con la política de celulares, si existe alguna urgencia usted debe solicitar permiso a su jefe inmediato para utilizar el celular, ¿usted solicitó o informó a su jefe inmediato sobre el uso de su celular?",
            "¿Usted es consciente que utilizar el celular en el área de trabajo es un riesgo físico para usted y sus compañeros?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente diligencia?"
        ]
    elif "retardo" in tipo or "tardanza" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Confirma usted que se presentó con un retardo en su hora de llegada de xxxx minutos el día xxxx?",
            "¿Tenía usted permiso para presentarse con un retardo de xxxx minutos el día xxxx?",
            "¿Tiene algún soporte que justifique el retraso de xxxx minutos en su hora de llegada el día xxxx?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Sabe usted que presentarse con un retraso puede ser considerado una falta grave?",
            "¿Sabe usted que está prohibido presentarse al puesto de trabajo con un retardo de hasta xxx minutos después de iniciada la jornada laboral?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente?"
        ]
    elif "daño" in tipo or "herramienta" in tipo or "equipo" in tipo:
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "¿Puede explicar cómo ocurrió el daño del equipo o herramienta?",
            "¿Estaba siguiendo el procedimiento adecuado al momento del daño?",
            "¿Había reportado algún desperfecto o falla previa?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Sabe que debe cuidar y utilizar adecuadamente las herramientas e instalaciones de la empresa?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente diligencia?"
        ]
    else:  # Caso "otros"
        return [
            "¿Cuánto tiempo lleva en la compañía y en el cargo?",
            "Describa brevemente los hechos que dieron lugar a esta diligencia.",
            "¿Tenía conocimiento de las normas aplicables a esta situación?",
            "¿Conoce el Reglamento Interno de Trabajo?",
            "¿Considera que cometió una falta?",
            "¿Quiere agregar algo más a la presente diligencia?"
        ]


# === GENERAR PREGUNTAS (actualizado) ===
def generar_preguntas_gemini(parsed: dict, max_ai=5):
    """Genera preguntas combinando base + 5 IA (más robusto)."""
    base = preguntas_base_por_tipo(parsed.get("tipo_falta", "otros"))

    if not API_KEY:
        return base

    prompt = f"""
Eres un asistente de Recursos Humanos especializado en diligencias de descargo laborales.

Genera {max_ai} preguntas adicionales para complementar una entrevista de descargo.
No repitas las preguntas base. Sé claro, neutral y enfocado en hechos verificables.

Contexto del caso:
- Tipo de falta: {parsed['tipo_falta']}
- Detalle: {parsed['detalle']}
- Artículos implicados: {parsed['articulos']}

Responde SOLO con una lista numerada de preguntas, sin explicaciones ni texto adicional.
Ejemplo de formato esperado:
1. ¿Pregunta 1?
2. ¿Pregunta 2?
3. ¿Pregunta 3?
4. ¿Pregunta 4?
5. ¿Pregunta 5?
"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content(prompt)

        raw_text = res.text.strip()
        print("\n=== Respuesta cruda de Gemini ===\n", raw_text, "\n========================\n")

        # Aceptar numeradas, con guiones o en texto corrido
        lines = re.split(r"[\n•\-]\s*", raw_text)
        ai_qs = [re.sub(r"^\d+\.\s*", "", l).strip() for l in lines if len(l.strip()) > 10]

        # Si el modelo devolvió un párrafo largo, intenta dividir por signos de interrogación
        if len(ai_qs) < 3:
            ai_qs = re.findall(r"¿[^?]+\?", raw_text)

        ai_qs = [q.strip() for q in ai_qs if q.endswith("?")][:max_ai]

        if not ai_qs:
            ai_qs = ["(La IA no generó preguntas adicionales correctamente.)"]

        return base + ai_qs

    except Exception as e:
        print("⚠️ Error con Gemini:", e)
        return base

# === GENERAR ACTA WORD ===
def generar_acta(parsed: dict, preguntas: list):
    """Llena la plantilla de acta Word con los datos de la citación."""
    doc = DocxTemplate(str(PLANTILLA_ACTA))

    # Construir el bloque de preguntas con formato
    bloque_preguntas = ""
    for i, p in enumerate(preguntas, start=1):
        bloque_preguntas += (
            f"PREGUNTA:\n{i}. {p}\n"
            f"RESPUESTA:\n\n\n"
        )
        bloque_preguntas += "_" * 80 + "\n\n"  # línea de separación visual

    contexto = {
        "nombre": parsed["nombre"],
        "fecha_citacion": parsed["fecha_citacion"],
        "fecha_hecho": parsed["fecha_hecho"],
        "detalle": parsed["detalle"],
        "articulos": parsed["articulos"],
        "preguntas": bloque_preguntas,
        "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    ACTAS_DIR.mkdir(exist_ok=True)
    salida = ACTAS_DIR / f"Acta_{parsed['nombre'].replace(' ', '_')}.docx"
    doc.render(contexto)
    doc.save(salida)
    print(f"✅ Acta generada: {salida}")
    return salida

# === MAIN ===
def main():
    archivos = [f for f in CITACIONES_DIR.glob("*.pdf")]
    if not archivos:
        print("No hay PDFs en la carpeta 'Citaciones/'.")
        return

    archivo = archivos[0]
    print(f"Procesando citación: {archivo.name}")

    texto = leer_texto_pdf(archivo)
    if len(texto) < 50:
        print("⚠️ No se extrajo texto suficiente. Verifica que el PDF no esté escaneado como imagen.")
        return

    print("✅ Texto extraído correctamente.")
    datos = extraer_datos_citacion(texto)
    print("📋 Datos extraídos:", datos)

    preguntas = generar_preguntas_gemini(datos)
    generar_acta(datos, preguntas)


#if __name__ == "__main__":
  # main()
