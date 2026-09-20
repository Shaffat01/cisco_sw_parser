from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

def parse_cisco_config(raw_text):
    data = {
        "hostname": "Unknown",
        "gateway": "Not Configured",
        "management_ips": [],
        "interfaces": [],
        "cdp": [],
        "vlans": []
    }

    # 1. Hostname
    host_match = re.search(r'hostname\s+(\S+)', raw_text, re.IGNORECASE)
    if host_match:
        data["hostname"] = host_match.group(1)

    # 2. Default Gateway
    gw_match = re.search(r'ip default-gateway\s+([\d\.]+)', raw_text, re.IGNORECASE)
    if gw_match:
        data["gateway"] = gw_match.group(1)

    # 3. VLAN IPs
    for match in re.finditer(r'interface vlan\s+(\d+).*?ip address\s+([\d\.]+)\s+([\d\.]+)', raw_text, re.IGNORECASE | re.DOTALL):
        data["management_ips"].append({
            "vlan": match.group(1),
            "ip": match.group(2),
            "mask": match.group(3)
        })

    # 4. Interface Configuration (Fixed Logic)
    int_blocks = re.split(r'\ninterface\s+', raw_text)
    for block in int_blocks[1:]:
        lines = block.splitlines()
        port_name = lines[0].strip()
        
        # Skip VLAN interfaces, process physical ports only
        if "vlan" in port_name.lower(): 
            continue 

        desc = "No Description"
        mode = "Access"
        vlans = "1 (Default)"

        for line in lines:
            line_clean = line.strip()
            line_lower = line_clean.lower()

            # Description
            if line_lower.startswith("description"):
                desc = line_clean[12:].strip()
                if desc.startswith("-"): desc = desc[1:].strip()

            # Access Mode & VLAN
            if "switchport mode access" in line_lower:
                mode = "Access"

            if "switchport access vlan" in line_lower:
                vlans = line_lower.split()[-1]

            # Trunk Mode & Allowed VLANs
            if "switchport mode trunk" in line_lower:
                mode = "Switch / Router Connection (Trunk)"

            if "switchport trunk allowed vlan" in line_lower:
                mode = "Trunk"
                if "add " in line_lower:
                    vlans = line_clean.split("add ")[-1].strip()
                else:
                    vlans = line_clean.split()[-1].strip()

            if "switchport trunk native vlan" in line_lower:
                mode = "Trunk"
                native_vlan = line_clean.split()[-1].strip()
                vlans = f"Native: {native_vlan}"

        data["interfaces"].append({
            "port": port_name.capitalize(),
            "description": desc if desc else "No Description",
            "mode": mode,
            "vlans": vlans
        })

    # 5. CDP Neighbors Detail Parser
    if "cdp neighbors" in raw_text.lower():
        cdp_blocks = re.split(r'---------------------------------------------', raw_text)
        for block in cdp_blocks:
            if "Device-ID:" in block or "Device ID:" in block:
                dev_id = re.search(r'Device[- ]ID:\s*(.+)', block, re.IGNORECASE)
                platform = re.search(r'Platform:\s*(.+?),', block, re.IGNORECASE)
                if not platform: platform = re.search(r'Platform:\s*([^\n]+)', block, re.IGNORECASE)
                local_int = re.search(r'Interface:\s*([^,]+)', block, re.IGNORECASE)
                port_id = re.search(r'Port ID[^\:]+:\s*(.+)', block, re.IGNORECASE)
                ip = re.search(r'IP\s+([\d\.]+)', block, re.IGNORECASE)

                data["cdp"].append({
                    "device": dev_id.group(1).strip() if dev_id else "Unknown",
                    "platform": platform.group(1).strip() if platform else "Unknown",
                    "local_port": local_int.group(1).strip() if local_int else "Unknown",
                    "remote_port": port_id.group(1).strip() if port_id else "Unknown",
                    "ip": ip.group(1).strip() if ip else "No IP"
                })

    # 6. VLAN Database
    vlan_section = re.search(r'Vlan\s+Name\s+Ports.*?\n\-+\s+\-+\s+\-+\s+\-+\s+\-+\n(.*?)(?=\n\S+#|\n\n|\Z)', raw_text, re.IGNORECASE | re.DOTALL)
    if vlan_section:
        vlan_lines = vlan_section.group(1).strip().splitlines()
        for line in vlan_lines:
            parts = re.split(r'\s{2,}', line.strip()) 
            if len(parts) >= 3:
                data["vlans"].append({
                    "id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "ports": parts[2].strip()
                })

    return data


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parse', methods=['POST'])
def parse_config():
    raw_text = request.json.get('text_data', '')
    if not raw_text:
        return jsonify({"status": "error", "message": "No text provided!"}), 400
    
    try:
        parsed_data = parse_cisco_config(raw_text)
        return jsonify({"status": "success", "data": parsed_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("\n🚀 Smart Config Parser Running on http://127.0.0.1:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=True)