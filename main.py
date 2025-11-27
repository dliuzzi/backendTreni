from io import BytesIO
import io
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import mysql.connector
import pandas as pd
from itertools import accumulate 

app = Flask(__name__)
CORS(app) 

DB_CONFIG = {
    'host': "localhost",
    'user': "root",
    'password': "",
    'database': "treni"
}

def get_db_connection():
    """Crea una nuova connessione per ogni richiesta"""
    conn = mysql.connector.connect(**DB_CONFIG)
    # buffered=True è fondamentale quando si fanno più query sullo stesso cursore
    # o quando non si leggono tutte le righe immediatamente.
    cursor = conn.cursor(dictionary=True, buffered=True) 
    return conn, cursor

@app.route("/treni")
def lista_treni():
    conn, cursor = get_db_connection()
    try:
        cursor.execute("SELECT treno_id, nome_treno, linea FROM rilevazioni_treni GROUP BY treno_id")
        treni = cursor.fetchall()
        return jsonify(treni)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Chiudiamo sempre connessione e cursore alla fine
        cursor.close()
        conn.close()

@app.route("/medie")
def medie():
    conn, cursor = get_db_connection()
    try:
        # Prima query
        cursor.execute("SELECT AVG(velocita) AS media_velocita, SUM(consumo_energetico) as totale_consumo, MAX(massa_sollevata) as massimo_massa FROM rilevazioni_treni")
        dati = cursor.fetchone()

        # Seconda query (ora sicura grazie a buffered=True e connessione isolata)
        cursor.execute("SELECT COUNT(*) as numero_anomalie FROM rilevazioni_treni WHERE velocita > 200 OR consumo_energetico > 5000 OR massa_sollevata > 10000")
        anomalie = cursor.fetchone()
        
        return jsonify({
            "medie": dati,
            "anomalie": anomalie['numero_anomalie']
        })
    finally:
        cursor.close()
        conn.close()

# --- FUNZIONE DI SUPPORTO ---
def get_time_filter(durata):
    filtro_tempo = None
    date_fmt = '%H:%M'
    
    if durata == 'giorno':
        filtro_tempo = "AND timestamp >= NOW() - INTERVAL 1 DAY"
        date_fmt = '%H:%M'
    elif durata == 'settimana':
        filtro_tempo = "AND timestamp >= NOW() - INTERVAL 7 DAY"
        date_fmt = '%d/%m'
    elif durata == 'mese':
        filtro_tempo = "AND timestamp >= NOW() - INTERVAL 1 MONTH"
        date_fmt = '%d/%m'
        
    return filtro_tempo, date_fmt

# 1. GRAFICO VELOCITÀ
@app.route("/treno/<int:id_treno>/velocita")
def grafico_velocita(id_treno):
    durata = request.args.get('durata', type=str)
    filtro_tempo, date_fmt = get_time_filter(durata)
    
    if filtro_tempo is None:
        return "Parametro 'durata' non valido.", 400

    conn, cursor = get_db_connection()
    try:
        query = f"SELECT timestamp, velocita FROM rilevazioni_treni WHERE treno_id = %s {filtro_tempo} ORDER BY timestamp"
        cursor.execute(query, (id_treno,))
        dati = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not dati:
        return "Nessun dato trovato.", 404

    times = [row['timestamp'] for row in dati]
    values = [row['velocita'] for row in dati]

    fig = Figure(figsize=(10, 6), dpi=100)
    ax = fig.subplots()
    ax.plot(times, values, color='#007ACC', linewidth=2, label='Velocità')
    ax.fill_between(times, values, color='#007ACC', alpha=0.1)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.set_ylabel('Velocità (km/h)', fontsize=12)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(DateFormatter(date_fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=45)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')


# 2. GRAFICO CONSUMO
@app.route("/treno/<int:id_treno>/consumo")
def grafico_consumo(id_treno):
    durata = request.args.get('durata', type=str)
    filtro_tempo, date_fmt = get_time_filter(durata)
    
    if filtro_tempo is None:
        return "Parametro 'durata' non valido.", 400

    conn, cursor = get_db_connection()
    try:
        query = f"SELECT timestamp, consumo_energetico FROM rilevazioni_treni WHERE treno_id = %s {filtro_tempo} ORDER BY timestamp"
        cursor.execute(query, (id_treno,))
        dati = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not dati:
        return "Nessun dato trovato.", 404

    times = [row['timestamp'] for row in dati]
    raw_consumi = [row['consumo_energetico'] for row in dati]
    cum_consumi = list(accumulate(raw_consumi))

    fig = Figure(figsize=(10, 6), dpi=100)
    ax = fig.subplots()
    ax.plot(times, cum_consumi, color='#2ca02c', linewidth=2, label='kWh Cumulativi')
    ax.fill_between(times, cum_consumi, color='#2ca02c', alpha=0.2)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.set_ylabel('Energia Totale (kWh)', fontsize=12)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(DateFormatter(date_fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=45)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')


# 3. GRAFICO CARICO
@app.route("/treno/<int:id_treno>/carico")
def grafico_carico(id_treno):
    durata = request.args.get('durata', type=str)
    filtro_tempo, date_fmt = get_time_filter(durata)
    
    if filtro_tempo is None:
        return "Parametro 'durata' non valido.", 400

    conn, cursor = get_db_connection()
    try:
        query = f"SELECT timestamp, massa_sollevata FROM rilevazioni_treni WHERE treno_id = %s {filtro_tempo} ORDER BY timestamp"
        cursor.execute(query, (id_treno,))
        dati = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not dati:
        return "Nessun dato trovato.", 404

    times = [row['timestamp'] for row in dati]
    masses = [row['massa_sollevata'] for row in dati]

    fig = Figure(figsize=(10, 6), dpi=100)
    ax = fig.subplots()

    if len(times) > 1:
        # 1. Convert python datetimes to matplotlib float dates (days)
        times_num = mdates.date2num(times)
        
        # 2. Calculate the difference between consecutive timestamps
        # (This assumes 'times' is already sorted from the SQL query)
        diffs = [times_num[i+1] - times_num[i] for i in range(len(times_num)-1)]
        
        # 3. Filter out zero differences (if duplicate timestamps exist)
        diffs = [d for d in diffs if d > 0]
        
        if diffs:
            min_diff = min(diffs)
            # Set width to 80% of the smallest gap found
            width = min_diff * 0.8 
        else:
            # Fallback if all timestamps are identical
            width = 0.01 
    else:
        width = 0.01

    ax.bar(times, masses, width=width, color='#ff7f0e', align='center', label='Tonnellate')
    ax.grid(True, linestyle='--', alpha=0.6, axis='y')
    ax.set_ylabel('Carico (Tonnellate)', fontsize=12)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(DateFormatter(date_fmt))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=45)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')

@app.route("/treno/<int:id_treno>/export/csv")
def export_csv(id_treno):
    durata = request.args.get('durata', default='giorno', type=str)
    filtro_tempo, _ = get_time_filter(durata)
    
    conn, cursor = get_db_connection()
    try:
        query = f"SELECT * FROM rilevazioni_treni WHERE treno_id = %s {filtro_tempo} ORDER BY timestamp DESC"
        cursor.execute(query, (id_treno,))
        dati = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not dati:
        return "Nessun dato da esportare per il periodo selezionato.", 404

    df = pd.DataFrame(dati)
    output = io.StringIO()
    df.to_csv(output, index=False, sep=';') 
    
    mem = io.BytesIO()
    mem.write(output.getvalue().encode('utf-8'))
    mem.seek(0)
    
    filename = f"treno_{id_treno}_dati_{durata}.csv"
    
    return Response(
        mem,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@app.route("/treno/<int:id_treno>/export/excel")
def export_excel(id_treno):
    durata = request.args.get('durata', default='giorno', type=str)
    filtro_tempo, _ = get_time_filter(durata)
    
    conn, cursor = get_db_connection()
    try:
        query = f"SELECT * FROM rilevazioni_treni WHERE treno_id = %s {filtro_tempo} ORDER BY timestamp DESC"
        cursor.execute(query, (id_treno,))
        dati = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    if not dati:
        return "Nessun dato da esportare.", 404

    df = pd.DataFrame(dati)
    
    if 'timestamp' in df.columns:
        df['timestamp'] = df['timestamp'].astype(str)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Dati Treno {id_treno}')
        worksheet = writer.sheets[f'Dati Treno {id_treno}']
        for column_cells in worksheet.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

    output.seek(0)
    filename = f"treno_{id_treno}_report_{durata}.xlsx"

    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)