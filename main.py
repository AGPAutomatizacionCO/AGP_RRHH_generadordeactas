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

# === EXTRACCIÓN DE DATOS ===
def extraer_datos_citacion(texto: str) -> dict:
    """Extrae los datos principales de una citación en PDF según el formato de AGP."""
    # Normalizar texto
    t = texto.replace("\r", " ").replace("\n", " ").strip()

    # Nombre del colaborador
    m = re.search(r"Señor\s*\(a\)\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ\s]+)", t)
    nombre = m.group(1).strip().title() if m else "No encontrado"

    # Fecha de la citación (ej: 25 de septiembre 2025 a las 4:00 p.m.)
    m = re.search(r"el día\s+([0-9]{1,2}\s+de\s+[a-zA-Zñ]+\s+\d{4}\s+a\s+las\s+[0-9:.\spm]+)", t)
    fecha_citacion = m.group(1).strip() if m else "No encontrada"

    # Fecha del hecho (ej: Cometidos el día: 2025-09-22)
    m = re.search(r"Cometidos el día[:\s]+([0-9\-\/]+)", t)
    fecha_hecho = m.group(1).strip() if m else "No encontrada"

    # Detalle del caso (entre "compañía:" y "Cometidos el día")
    m = re.search(
        r"compañía[:\-]?\s*(.+?)Cometidos el día",
        t, re.IGNORECASE | re.DOTALL)
    detalle = m.group(1).strip() if m else "No se encontró detalle"

    # Artículos citados
    
    articulos = extraer_articulos_completos(texto)


    return {
        "nombre": nombre,
        "fecha_citacion": fecha_citacion,
        "fecha_hecho": fecha_hecho,
        "detalle": detalle,
        "articulos": articulos
    }


# === GENERAR PREGUNTAS CON GEMINI ===
def generar_preguntas_gemini(parsed: dict, max_q=10):
    """Genera preguntas de descargo con Gemini (o genéricas si no hay API key)."""
    if not API_KEY:
        return [

            "¿Puede explicar los hechos que llevaron al incumplimiento?",
            "¿Por qué no se realizó la verificación correspondiente?",
            "¿Conocía el procedimiento correcto para esta operación?",
            "¿Hubo alguna situación que le impidiera cumplirlo?",
            "¿Qué medidas propone para evitar que vuelva a suceder?"
        ]

    prompt = f"""
Eres un asistente de Recursos Humanos que genera preguntas para diligencias de descargo laborales.

Contexto del caso:
- Colaborador: {parsed['nombre']}
- Fecha del hecho: {parsed['fecha_hecho']}
- Detalle del caso: {parsed['detalle']}
- Artículos implicados: {', '.join(parsed['articulos'])}

Tu tarea:
Genera exactamente {max_q} preguntas claras, neutrales y enfocadas en los hechos,
que permitan al colaborador explicar su versión de los acontecimientos.

Requisitos:
- No escribas introducciones, saludos ni frases como "aquí tienes" o "estas son".
- No uses asteriscos, comillas ni Markdown.
- No incluyas explicaciones o contexto adicional.
- Entrega únicamente la lista numerada de preguntas, una por línea, con este formato:

1. ¿Pregunta 1?
2. ¿Pregunta 2?
3. ¿Pregunta 3?
"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content(prompt)
        lines = [l.strip("-•0123456789. ").strip() for l in res.text.split("\n") if len(l.strip()) > 5]
        return lines[:max_q]
    except Exception as e:
        print("⚠️ Error con Gemini:", e)
        return [
            "Explique los hechos desde su perspectiva.",
            "¿Tiene alguna justificación o prueba sobre lo ocurrido?"
        ]
# === GENERAR ACTA WORD ===
def generar_acta(parsed: dict, preguntas: list):
    """Llena la plantilla de acta Word con los datos de la citación."""
    doc = DocxTemplate(str(PLANTILLA_ACTA))
    contexto = {
        "nombre": parsed["nombre"],
        "fecha_citacion": parsed["fecha_citacion"],
        "fecha_hecho": parsed["fecha_hecho"],
        "detalle": parsed["detalle"],
        "articulos": parsed["articulos"],
        "preguntas": "\n".join([f"{i+1}. {p}" for i, p in enumerate(preguntas)]),
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
 #   main()
