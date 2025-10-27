import streamlit as st
from pathlib import Path
from main import (
    leer_texto_pdf,
    extraer_datos_citacion,
    generar_preguntas_gemini,
    generar_acta,
)

st.set_page_config(page_title="Generador de Actas RRHH", page_icon="📄", layout="wide")
st.title("📋 Generador de Actas de Descargo")

# --- Subir PDF ---
st.header("1️⃣ Cargar Citación")
archivo_pdf = st.file_uploader("Sube el documento PDF de la citación", type=["pdf"])

if archivo_pdf:
    # Guardar temporalmente el PDF subido
    temp_path = Path("temp_citacion.pdf")
    with open(temp_path, "wb") as f:
        f.write(archivo_pdf.read())

    st.success("✅ Documento cargado correctamente.")
    texto = leer_texto_pdf(temp_path)

    if len(texto) < 50:
        st.error("❌ No se pudo leer texto del PDF (puede estar escaneado como imagen).")
        st.stop()

    # --- Extraer datos ---
    datos = extraer_datos_citacion(texto)

    st.header("2️⃣ Datos extraídos de la citación")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nombre del colaborador", datos["nombre"], key="nombre")
        st.text_input("Fecha de citación", datos["fecha_citacion"], key="fecha_citacion")
    with col2:
        st.text_input("Fecha del hecho", datos["fecha_hecho"], key="fecha_hecho")
        st.text_area("Detalle del caso", datos["detalle"], height=120, key="detalle")

    st.text_area("Artículos citados", datos["articulos"], height=180, key="articulos")

    # --- Generar preguntas con IA ---
    st.header("3️⃣ Preguntas generadas automáticamente")
    if st.button("Generar preguntas con IA"):
        with st.spinner("Generando preguntas con Gemini..."):
            preguntas = generar_preguntas_gemini(datos)

        st.session_state["preguntas"] = preguntas
        st.success("✅ Preguntas generadas exitosamente.")

    # Si ya hay preguntas en la sesión, mostrarlas editable
    if "preguntas" in st.session_state:
        st.subheader("✏️ Revisar o editar preguntas")
        nuevas_preguntas = []
        for i, pregunta in enumerate(st.session_state["preguntas"]):
            nuevas_preguntas.append(st.text_input(f"Pregunta {i+1}", pregunta, key=f"preg_{i}"))

        st.session_state["preguntas"] = nuevas_preguntas

        # --- Generar acta final ---
        st.header("4️⃣ Generar acta final")
        if st.button("Generar Acta Word"):
            with st.spinner("Creando documento Word..."):
                salida = generar_acta(datos, st.session_state["preguntas"])
            st.success(f"✅ Acta generada correctamente: {salida}")
            with open(salida, "rb") as f:
                st.download_button("⬇️ Descargar Acta Word", f, file_name=Path(salida).name)
