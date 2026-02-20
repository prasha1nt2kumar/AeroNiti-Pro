from flask import Flask, render_template, request, jsonify
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import numpy as np
from math import radians, cos, sin, asin, sqrt

app = Flask(__name__)

# --- DATA LOADING ENGINE (BULLETPROOF CLEANING) ---
def load_data():
    data = {}
    def clean_name(name):
        if not isinstance(name, str): return str(name)
        return name.split('/')[0].split('(')[0].strip().title()

    try:
        routes = pd.read_csv("Master_Routes.csv")
        routes['Origin'] = routes['Origin'].apply(clean_name)
        routes['Destination'] = routes['Destination'].apply(clean_name)
        data['valid_set'] = set(routes['Origin'].unique()) | set(routes['Destination'].unique())
        data['distances'] = {(row['Origin'], row['Destination']): row['Distance_Km'] for _, row in routes.iterrows()}
    except:
        data['distances'], data['valid_set'] = {}, set()

    try:
        df = pd.read_csv("Master_Airports.csv")
        
        # Clean Coordinates Safely
        for c in ['Latitude', 'Longitude']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.replace(r'[^\d.-]', '', regex=True)
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
                
        # Clean Financials Aggressively to protect Delhi/Mopa massive numbers
        for c in ['2025', 'Per Capita Income']: 
            if c in df.columns: 
                df[c] = df[c].astype(str).str.replace(r'[^\d.]', '', regex=True)
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        if 'Demand Type' in df.columns:
            df['Demand Type'] = df['Demand Type'].astype(str).str.strip().str.title().replace(['Nan','nan',''], np.nan)
            
        df['Match_Name'] = df['Area served'].apply(clean_name)
        data['airports'] = df[df['Match_Name'].isin(data['valid_set'])].copy() if data['valid_set'] else df
    except:
        data['airports'] = pd.DataFrame()
    return data

bundle = load_data()
df = bundle['airports']
dist_lookup = bundle['distances']

# --- MATH FUNCTIONS ---
def get_dist(c1, c2, lat1, lon1, lat2, lon2):
    def clean(n): return n.split('/')[0].split('(')[0].strip().title()
    k1, k2 = clean(str(c1)), clean(str(c2))
    if (k1, k2) in dist_lookup: return int(dist_lookup[(k1, k2)])
    if lat1 == 0 or lat2 == 0: return 0
    lo1, la1, lo2, la2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    return int(2 * asin(sqrt(sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2)) * 6371)

def calc_econ(dist_km, plane):
    p = {"ATR": (500, 72, 150000, 1500), "Airbus": (840, 180, 450000, 6000)}
    key = "ATR" if "ATR" in plane else "Airbus"
    speed, seats, cost_hr, rng = p[key]
    time = (dist_km / speed) + 0.5
    fuel = time * (600 if key=="ATR" else 2400)
    co2 = time * (1900 if key=="ATR" else 7500)
    breakeven = (time * cost_hr) / (seats * 0.8)
    return round(time, 1), int(breakeven), rng, int(fuel), int(co2)

# --- ROUTES ---
@app.route('/')
def index():
    if df.empty:
        return render_template('index.html', hubs=[], pilgrimages=[], total=0, critical=0, pilgrim=0)
    
    total_airports = len(df)
    critical_count = len(df[(df['2025'] > 0) & (df['2025'] < 15000)])
    pilgrim_count = len(df[df['Demand Type'] == 'Pilgrimage'])
    hubs = sorted(df[df['Airport Category'].astype(str).str.contains('Hub', case=False, na=False)]['Area served'].unique())
    pilg = sorted(df[df['Demand Type'] == 'Pilgrimage']['Area served'].unique())
    
    return render_template('index.html', hubs=hubs, pilgrimages=pilg, total=total_airports, critical=critical_count, pilgrim=pilgrim_count)

# --- API: VIABILITY SIMULATOR ---
@app.route('/api/viability', methods=['POST'])
def analyze_viability():
    data = request.json
    thresh = int(data.get('threshold', 5000))
    boost = int(data.get('boost', 0))
    
    sim = df.copy()
    sim['Simulated'] = sim['2025'] * (1 + boost/100)
    sim['Status'] = np.where((sim['2025']<=0), 'No Data', np.where(sim['Simulated']<thresh, 'Critical', 'Viable'))
    
    saved = len(sim[(sim['2025'] < thresh) & (sim['Simulated'] >= thresh)])
    critical = len(sim[sim['Status']=='Critical'])
    viable = len(sim[sim['Status']=='Viable'])
    
    if boost > 0 and saved > 0:
        insight, color = f"💡 <b>Policy Success:</b> The {boost}% subsidy rescued {saved} airports.", "bg-blue-50 border-blue-500 text-blue-900"
    elif critical > (len(sim)*0.3):
        insight, color = f"⚠️ <b>Systemic Risk:</b> Over 30% ({critical} airports) unviable.", "bg-red-50 border-red-500 text-red-900"
    else:
        insight, color = "✅ <b>Robust Network:</b> The network is stable.", "bg-green-50 border-green-500 text-green-900"
        
    fig = px.scatter(sim[sim['Status']!='No Data'], x="Simulated", y="Area served", color="Status", color_discrete_map={'Viable':'#0066CC', 'Critical':'#FF4B4B'})
    fig.update_layout(margin={"r":0,"t":30,"l":0,"b":0})
    return jsonify({"viable": viable, "critical": critical, "insight": insight, "color": color, "chart": pio.to_json(fig)})

# --- API: RESILIENCE STRESS-TEST ---
@app.route('/api/resilience', methods=['POST'])
def analyze_resilience():
    scenario = request.json.get('scenario', 'Baseline')
    if "Baseline" in scenario:
        insight, color, mults = "✅ Market Stability: Balanced growth across sectors.", "bg-green-50 border-green-500", {'Industrial':1.0, 'Leisure':1.0, 'Pilgrimage':1.0}
    elif "Recession" in scenario:
        insight, color, mults = "📉 Strategy: Corporate travel hit hard. Pilgrimage resilient.", "bg-yellow-50 border-yellow-500", {'Industrial':0.7, 'Leisure':0.8, 'Pilgrimage':0.95}
    else:
        insight, color, mults = "🦠 Strategy: Leisure collapses. Pilgrimage is the safety net.", "bg-red-50 border-red-500", {'Industrial':0.4, 'Leisure':0.3, 'Pilgrimage':0.7}
        
    sim = df.copy()
    sim['Proj'] = sim['2025'] * sim['Demand Type'].map(mults).fillna(1.0)
    grp = sim.dropna(subset=['Demand Type']).groupby('Demand Type')[['2025', 'Proj']].sum().reset_index()
    
    x_vals = grp['Demand Type'].tolist()
    y_normal = grp['2025'].tolist()
    y_stress = grp['Proj'].tolist()
    text_labels = [f"{val:.1f}%" for val in ((grp['Proj'] / grp['2025'] - 1) * 100)]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(name='Normal', x=x_vals, y=y_normal, marker_color='#B0C4DE'))
    fig.add_trace(go.Bar(name='Stress', x=x_vals, y=y_stress, marker_color='#0066CC', text=text_labels, textposition='auto'))
    fig.update_layout(barmode='group', margin={"r":0,"t":30,"l":0,"b":0})
    
    return jsonify({"insight": insight, "color": color, "chart": pio.to_json(fig)})

# --- API: EXPANSION SCOUT (DELHI/MOPA FLIP + BULLETPROOF MAP) ---
@app.route('/api/expansion', methods=['POST'])
def analyze_expansion():
    w = float(request.json.get('weight', 0.7))
    scout = df.copy()

    max_inc = scout['Per Capita Income'].max()
    max_pax = scout['2025'].max()
    
    if max_inc == 0: max_inc = 1
    if max_pax == 0: max_pax = 1

    scout['Income_Score'] = scout['Per Capita Income'] / max_inc
    scout['Opportunity_Score'] = scout['2025'] / max_pax

    scout['Score'] = (scout['Income_Score'] * w) + (scout['Opportunity_Score'] * (1 - w))
    
    top = scout.sort_values('Score', ascending=False)
    winner = top.iloc[0]
    
    reason = "It represents a massive, established high-traffic market." if w < 0.5 else "It possesses exceptional ticket-paying capacity."
    insight = f"🏆 <b>Top Target:</b> {winner['Area served']} ({winner['State']}). {reason}"
    
    # Filter out missing coordinates for the map
    map_df = top[top['Latitude'] != 0.0].head(20)
    
    # Convert Pandas Series to pure Python Lists to prevent JSON/Plotly rendering bugs
    lats = map_df['Latitude'].tolist()
    lons = map_df['Longitude'].tolist()
    bubble_sizes = ((map_df['Score'] * 25) + 12).tolist() 
    bubble_colors = map_df['Score'].tolist()
    hover_texts = (map_df['Area served'] + "<br>Score: " + (map_df['Score']*100).round(1).astype(str) + "%").tolist()
    
    fig = go.Figure(go.Scattermapbox(
        lat=lats,
        lon=lons,
        mode='markers',
        marker=dict(
            size=bubble_sizes,
            color=bubble_colors,
            colorscale='Viridis',
            showscale=True
        ),
        text=hover_texts,
        hoverinfo='text'
    ))
    
    fig.update_layout(
        mapbox_style="carto-positron",
        margin={"r":0,"t":0,"l":0,"b":0},
        mapbox=dict(zoom=3.8, center=dict(lat=22.0, lon=79.0)) 
    )

    table_df = top[['Area served', 'State', 'Per Capita Income', 'Score']].head(5).copy()
    table_df = table_df.rename(columns={'Area served': 'Target City', 'Per Capita Income': 'Avg. Income', 'Score': 'Opportunity Score'})
    table_df['Avg. Income'] = table_df['Avg. Income'].apply(lambda x: f"₹ {int(x):,}")
    table_df['Opportunity Score'] = table_df['Opportunity Score'].apply(lambda x: f"{x * 100:.1f}%")
    
    table_html = table_df.to_html(classes='w-full text-left border-collapse', index=False, border=0, justify='left')
    
    return jsonify({"insight": insight, "map_data": pio.to_json(fig), "table": table_html})

# --- API: YATRA CONNECT (SHORTEST PATH OPTIMIZATION) ---
@app.route('/api/analyze_circuit', methods=['POST'])
def analyze_circuit():
    data = request.json
    h, p, plane = data['hub'], data['pilgrimage'], data['plane']
    if df.empty: return jsonify({"error": "Data missing"})

    h_r = df[df['Area served'] == h].iloc[0]
    p_r = df[df['Area served'] == p].iloc[0]
    
    # Calculate distance for Leg 1
    d1 = get_dist(h, p, h_r['Latitude'], h_r['Longitude'], p_r['Latitude'], p_r['Longitude'])
    
    best_city = "Unknown"
    shortest_circuit_dist = float('inf')
    
    # LOOP OPTIMIZATION: Find the mathematically shortest triangular circuit
    for index, row in df.iterrows():
        c_candidate = row['Area served']
        if c_candidate in [h, p] or row['Latitude'] == 0.0: 
            continue 
            
        d2_temp = get_dist(p, c_candidate, p_r['Latitude'], p_r['Longitude'], row['Latitude'], row['Longitude'])
        d3_temp = get_dist(c_candidate, h, row['Latitude'], row['Longitude'], h_r['Latitude'], h_r['Longitude'])
        
        total_d = d1 + d2_temp + d3_temp
        
        if total_d < shortest_circuit_dist:
            shortest_circuit_dist = total_d
            best_city = c_candidate

    c_name = best_city if best_city != "Unknown" else df.iloc[0]['Area served']
    c_r = df[df['Area served'] == c_name].iloc[0]
    
    # Final distances for the winning route
    d2 = get_dist(p, c_name, p_r['Latitude'], p_r['Longitude'], c_r['Latitude'], c_r['Longitude'])
    d3 = get_dist(c_name, h, c_r['Latitude'], c_r['Longitude'], h_r['Latitude'], h_r['Longitude'])
    total_dist = d1 + d2 + d3
    
    time, tix, max_rng, fuel, co2 = calc_econ(total_dist, plane)
    
    longest_leg = max(d1, d2, d3)
    is_strategic = c_r['2025'] < 50000 

    if longest_leg > max_rng:
        insight, tag, color = f"❌ <b>Operational Warning:</b> INFEASIBLE. Longest leg ({longest_leg} km) exceeds range.", "<span class='text-red-600 font-black'> (⛔)</span>", "bg-red-50 border-red-500 text-red-900"
    elif is_strategic:
        insight, tag, color = f"💡 <b>Strategic Value:</b> Connects {c_name} (Critical) to stable traffic. Acts as a 'Traffic Subsidy'.", "<span class='text-yellow-600 font-black'> (⚠️)</span>", "bg-blue-50 border-blue-500 text-blue-900"
    else:
        insight, tag, color = "⚡ <b>Efficiency:</b> High-Performance route connecting stable nodes.", "<span class='text-green-600 font-black'> (✅)</span>", "bg-green-50 border-green-500 text-green-900"
    
    lats = [h_r['Latitude'], p_r['Latitude'], c_r['Latitude'], h_r['Latitude']]
    lons = [h_r['Longitude'], p_r['Longitude'], c_r['Longitude'], h_r['Longitude']]
    mid_lats = [(lats[i] + lats[i+1])/2 for i in range(3)]
    mid_lons = [(lons[i] + lons[i+1])/2 for i in range(3)]
    
    labels = [f"{d1} km", f"{d2} km", f"{d3} km"]

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(mode="lines+markers", lon=lons, lat=lats, marker={'size': 10, 'color':'#0066CC'}, line={'width': 3, 'color': '#0066CC'}))
    fig.add_trace(go.Scattermapbox(mode="text", lon=mid_lons, lat=mid_lats, text=labels, textfont=dict(size=14, color='black', family="Arial Black"), hoverinfo='skip'))
    fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0}, mapbox=dict(zoom=3.8, center=dict(lat=np.mean(lats), lon=np.mean(lons))), showlegend=False)

    return jsonify({
        "circuit_html": f"{h} ➝ {p} ➝ {c_name}{tag} ➝ {h}", 
        "insight": insight, 
        "color": color, 
        "distance": total_dist, 
        "time": time, 
        "price": tix, 
        "fuel": fuel, 
        "co2": co2, 
        "map_data": pio.to_json(fig)
    })

if __name__ == '__main__':
    app.run(debug=True)