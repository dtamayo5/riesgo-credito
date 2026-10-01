"""
Mensajes, acciones y conclusiones redactados por reglas.

  mensajes_comite()   -> lista de (tono, texto) para el resumen del comité
  acciones()          -> lista de dict(prioridad, accion, monto, sustento)
  fortalezas_riesgos() -> dos listas para el informe de fondeadores

Cada cifra sale de los resultados del corte; el tono sale del semáforo:
rojo si el límite relacionado está excedido, ámbar si está en alerta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utilidades import millones, num, pct

_ORDEN = {"rojo": 0, "ambar": 1, "info": 2, "verde": 3}


def _tono(estados: dict, *codigos) -> str:
    v = [estados.get(c) for c in codigos]
    return "rojo" if "ROJO" in v else "ambar" if "ÁMBAR" in v else "info"


def _cosecha_txt(q: str) -> str:
    """'2026Q1' -> 'primer trimestre de 2026'."""
    nombres = {"1": "primer", "2": "segundo", "3": "tercer", "4": "cuarto"}
    return f"{nombres.get(q[-1], '')} trimestre de {q[:4]}" if len(q) == 6 else q


def _escenario(nombre: str) -> str:
    n = nombre.lower()
    return "de " + n if n.startswith("estrés") else n


def punto_corte_sugerido(sc) -> pd.Series | None:
    """Menor rechazo adicional que devuelve la tasa de malos al nivel del desarrollo."""
    objetivo = sc.metricas["Desarrollo"]["tasa_malos"]
    c = sc.cortes[sc.cortes["rechazo"] > 0]
    ok = c[c["tasa_malos"] <= objetivo]
    fila = ok.iloc[0] if len(ok) else c[c["rechazo"] <= 0.20].iloc[-1]
    return fila


def mensajes_comite(r: dict) -> list[tuple[str, str]]:
    lim, ind, foto, ev = r["limites"], r["indicadores"], r["foto"], r["evolucion"]
    est = dict(zip(lim["codigo"], lim["estado"]))
    r9, fon, es, sc = r["niif9"], r["fondeo"], r["estres"], r["score"]
    pat = r["entidad"]["patrimonio"]
    m = []

    # 1. Calidad de cartera y su tendencia
    hace = ev.iloc[max(len(ev) - 7, 0)]
    prod = r["productos"]
    peor = prod["icv30"].idxmax()
    m.append((_tono(est, "ICV_30", "ICV_90"),
              f"La cartera vencida a más de 30 días es {pct(foto['icv30'])} ({millones(foto['saldo_30'])}) y a más de "
              f"90 días {pct(foto['icv90'])}; hace seis meses eran {pct(hace['icv30'])} y {pct(hace['icv90'])}. "
              f"El producto con peor indicador es {peor} ({pct(prod.loc[peor, 'icv30'])} a 30 días)."))

    # 2. Cosechas
    q, v, ref = r["cosecha_mob6"]
    if q:
        veces = v / ref if ref else np.nan
        texto = (f"La cosecha del {_cosecha_txt(q)} llega a seis meses de vida con {pct(v)} de sus créditos "
                 f"en mora de más de 30 días, frente a {pct(ref)} en promedio de las cosechas anteriores")
        texto += f" ({num(veces, 1)} veces)." if veces >= 1.2 else "."
        pd_r, pd_d = sc.metricas["pd_reciente"], sc.metricas["pd_desarrollo"]
        if pd_r > pd_d * 1.10:
            texto += (f" Parte del deterioro viene del perfil aprobado: la PD de originación de los últimos seis "
                      f"meses es {pct(pd_r)}, frente a {pct(pd_d)} en la muestra de desarrollo del score (PSI "
                      f"{num(sc.metricas['psi'], 2)}).")
        else:
            texto += (" El perfil de los aprobados no cambió (PSI "
                      f"{num(sc.metricas['psi'], 2)}): el deterioro es del entorno, no de la originación.")
        m.append((_tono(est, "COSECHA_MOB6"), texto))

    # 3. Provisiones
    reg = r["entidad"]["prov_registrada"]
    texto = (f"La pérdida esperada NIIF 9 es {millones(r9.ecl)} ({pct(r9.ecl / foto['cartera'])} de la cartera y "
             f"{pct(ind['COBERTURA_30'], 0)} de la cartera vencida a 30 días); la referencia regulatoria por altura "
             f"de mora da {millones(r9.ref_total)}.")
    if not np.isnan(reg):
        brecha = r9.ecl - reg
        if brecha > 0:
            texto += (f" La provisión registrada ({millones(reg)}) queda {millones(brecha)} por debajo de la NIIF 9, "
                      f"equivalente al {pct(brecha / pat)} del patrimonio.")
        else:
            texto += f" La provisión registrada ({millones(reg)}) cubre la NIIF 9 con un exceso de {millones(-brecha)}."
    tono = _tono(est, "COBERTURA_30")
    if not np.isnan(reg) and r9.ecl - reg > 0.10 * pat:
        tono = "rojo"
    m.append((tono, texto))

    # 4. Estrés
    t = es["tabla"]
    if len(t):
        sev = t.sort_values("ecl_adicional").iloc[-1]
        inv = es["inverso"]
        texto = (f"En el escenario {_escenario(sev['escenario'])} (PD x {num(sev['mult_pd'], 2)}, LGD +"
                 f"{num(100 * sev['ajuste_lgd'], 0)} pp) las provisiones subirían {millones(sev['ecl_adicional'])}, "
                 f"el {pct(sev['pct_patrimonio'])} del patrimonio, y el {pct(sev['saldo_etapa2'], 0)} de la cartera "
                 f"pasaría a etapa 2.")
        if not np.isnan(inv["consume_umbral"]):
            texto += (f" Estrés inverso: con la PD multiplicada por {num(inv['consume_umbral'], 2)} se consumiría el "
                      f"{pct(inv['umbral_patrimonio'], 0)} del patrimonio.")
        m.append((_tono(est, "ESTRES_SEVERO_PAT"), texto))

    # 5. Fondeo
    texto = (f"La cartera elegible ({millones(fon['elegible'])}) por la tasa de anticipo de {pct(fon['anticipo'], 0)} "
             f"cubre {num(fon['cobertura'], 2)} veces la deuda con fondeadores")
    texto += (f"; la holgura es de solo {millones(fon['holgura'])}." if fon["cobertura"] < 1.10 and fon["holgura"] >= 0 else
              f"; faltan {millones(-fon['holgura'])} de base de préstamo." if fon["holgura"] < 0 else
              f" (holgura {millones(fon['holgura'])}).")
    texto += (f" El excedente financiero es {pct(fon['excedente'])} anual: la PD tendría que multiplicarse por "
              f"{num(fon['equilibrio_pd'], 2)} para llevarlo a cero.")
    m.append((_tono(est, "COBERTURA_DEUDA", "EXCEDENTE_FIN"), texto))

    # 6. Modelo
    g_oot, g_dev = sc.metricas["Fuera de tiempo"]["gini"], sc.metricas["Desarrollo"]["gini"]
    m.append((_tono(est, "GINI_OOT", "PSI"),
              f"El score de originación separa bien buenos de malos: Gini de {pct(g_oot)} en créditos que no vio "
              f"(fuera de tiempo) y {pct(g_dev)} en desarrollo; KS {pct(sc.metricas['Fuera de tiempo']['ks'])}."))

    # 7. Otros límites en rojo o ámbar sin mensaje propio
    propios = {"ICV_30", "ICV_90", "COSECHA_MOB6", "COBERTURA_30", "ESTRES_SEVERO_PAT", "COBERTURA_DEUDA",
               "EXCEDENTE_FIN", "GINI_OOT", "PSI"}
    for _, l in lim[lim["estado"].isin(["ROJO", "ÁMBAR"]) & ~lim["codigo"].isin(propios)].iterrows():
        ind_txt = l["indicador"][0].lower() + l["indicador"][1:]
        m.append(("rojo" if l["estado"] == "ROJO" else "ambar",
                  f"{'Límite excedido' if l['estado'] == 'ROJO' else 'En alerta'}: {ind_txt} en {l['valor_txt']} "
                  f"(límite {l['limite_txt']}){' - ' + l['detalle'] if l['detalle'] else ''}."))

    # 8. Datos
    h = r["hallazgos"]
    if h.conteo("ERROR") or h.conteo("ADVERTENCIA"):
        m.append(("info", f"Calidad de datos: {h.conteo('ERROR')} errores y {h.conteo('ADVERTENCIA')} advertencias "
                          f"corregidos automáticamente y documentados en la sección de calidad de datos."))
    return sorted(m, key=lambda x: _ORDEN[x[0]])


def acciones(r: dict) -> list[dict]:
    lim, foto = r["limites"], r["foto"]
    est = dict(zip(lim["codigo"], lim["estado"]))
    lim_i = lim.set_index("codigo")
    r9, fon, es, sc, e = r["niif9"], r["fondeo"], r["estres"], r["score"], r["entidad"]
    pat = e["patrimonio"]
    salida = []

    reg = e["prov_registrada"]
    if not np.isnan(reg) and r9.ecl > reg:
        salida.append({"prioridad": "Alta" if r9.ecl - reg > 0.10 * pat else "Media",
                       "accion": "Ajustar la provisión contable a la pérdida esperada NIIF 9",
                       "monto": r9.ecl - reg,
                       "sustento": f"ECL {millones(r9.ecl)} frente a {millones(reg)} registrados"})
    if not np.isnan(reg) and r9.ref_total > reg:
        salida.append({"prioridad": "Alta", "accion": "Cubrir al menos la referencia regulatoria por altura de mora",
                       "monto": r9.ref_total - reg,
                       "sustento": f"Referencia {millones(r9.ref_total)} frente a {millones(reg)} registrados"})

    if est.get("COSECHA_MOB6") in ("ROJO", "ÁMBAR") or sc.metricas["pd_reciente"] > 1.05 * sc.metricas["pd_desarrollo"]:
        c = punto_corte_sugerido(sc)
        if c is not None:
            base = sc.cortes.iloc[0]["tasa_malos"]
            salida.append({"prioridad": "Alta" if est.get("COSECHA_MOB6") == "ROJO" else "Media",
                           "accion": f"Subir el punto de corte del score a {num(c['corte'])} puntos",
                           "monto": np.nan,
                           "sustento": (f"Rechaza {pct(c['rechazo'], 0)} de las solicitudes y baja la tasa de malos de "
                                        f"{pct(base)} a {pct(c['tasa_malos'])} (validación fuera de tiempo)")})

    alerta_cob = float(lim_i.loc["COBERTURA_DEUDA", "alerta"]) if "COBERTURA_DEUDA" in lim_i.index else 1.10
    if fon["deuda"] and fon["cobertura"] < alerta_cob:
        aporte = alerta_cob * fon["deuda"] / fon["anticipo"] - fon["elegible"]
        prepago = fon["deuda"] - fon["base_prestamo"] / alerta_cob
        salida.append({"prioridad": "Alta" if fon["cobertura"] < 1 else "Media",
                       "accion": f"Llevar la cobertura de la deuda a {num(alerta_cob, 2)} veces",
                       "monto": aporte,
                       "sustento": f"Aportar {millones(aporte)} de cartera elegible o prepagar {millones(prepago)} de deuda"})

    t = es["tabla"]
    if len(t) and "ESTRES_SEVERO_PAT" in lim_i.index:
        sev = t.sort_values("ecl_adicional").iloc[-1]
        limite = float(lim_i.loc["ESTRES_SEVERO_PAT", "limite"])
        if sev["pct_patrimonio"] > limite:
            capital = sev["ecl_adicional"] / limite - pat
            salida.append({"prioridad": "Alta", "accion": "Fortalecer el patrimonio o reducir el crecimiento",
                           "monto": capital,
                           "sustento": (f"Capital adicional para que el escenario {_escenario(sev['escenario'])} quede "
                                        f"dentro del límite de {pct(limite, 0)} del patrimonio")})

    if "EXCEDENTE_FIN" in lim_i.index and fon["excedente"] < float(lim_i.loc["EXCEDENTE_FIN", "alerta"]):
        falta = float(lim_i.loc["EXCEDENTE_FIN", "alerta"]) - fon["excedente"]
        pb = falta / max(fon["rendimiento"] / max(foto["tasa_promedio"], 1e-9), 1e-9) * 10_000
        salida.append({"prioridad": "Media", "accion": "Recuperar el excedente financiero",
                       "monto": falta * foto["cartera"],
                       "sustento": f"Subir la tasa promedio en {num(pb)} pb o reducir gastos en el mismo monto anual"})

    if est.get("PSI") in ("ROJO", "ÁMBAR") or est.get("GINI_OOT") == "ROJO":
        salida.append({"prioridad": "Media", "accion": "Recalibrar el score con las cosechas recientes",
                       "monto": np.nan, "sustento": "La población o el poder discriminante cambiaron frente al desarrollo"})

    h = r["hallazgos"]
    if h.conteo("ERROR") + h.conteo("ADVERTENCIA"):
        salida.append({"prioridad": "Baja", "accion": "Corregir en el origen los datos señalados",
                       "monto": np.nan,
                       "sustento": f"{h.conteo('ERROR') + h.conteo('ADVERTENCIA')} hallazgos con archivo y fila"})
    orden = {"Alta": 0, "Media": 1, "Baja": 2}
    return sorted(salida, key=lambda a: orden[a["prioridad"]])


def fortalezas_riesgos(r: dict) -> tuple[list[str], list[str]]:
    lim, foto, ev = r["limites"], r["foto"], r["evolucion"]
    est = dict(zip(lim["codigo"], lim["estado"]))
    fon, sc, conc, r9 = r["fondeo"], r["score"], r["concentracion"], r["niif9"]
    F, R = [], []
    crec = ev["cartera"].iloc[-1] / ev["cartera"].iloc[0] - 1
    F.append(f"Cartera de {millones(foto['cartera'])} en {num(foto['n_creditos'])} créditos; crecimiento de "
             f"{pct(crec, 0)} en 12 meses con ticket promedio de {millones(foto['ticket_promedio'], 1)}.")
    (F if conc["top20"] < 0.10 else R).append(
        f"Los 20 mayores deudores suman el {pct(conc['top20'])} de la cartera"
        + (": riesgo atomizado." if conc["top20"] < 0.10 else ": concentración relevante."))
    (F if fon["excedente"] > 0 else R).append(
        f"Excedente financiero de {pct(fon['excedente'])} anual después de pérdida esperada; el punto de equilibrio "
        f"exige multiplicar la PD por {num(fon['equilibrio_pd'], 2)}.")
    (F if fon["cobertura"] >= 1.10 else R).append(
        f"Cobertura de la deuda de {num(fon['cobertura'], 2)} veces con anticipo de {pct(fon['anticipo'], 0)} "
        f"sobre cartera con mora de hasta {r['entidad']['dias_elegible']} días"
        + ("." if fon["cobertura"] >= 1.10 else f"; holgura de {millones(fon['holgura'])}."))
    (F if est.get("GINI_OOT") != "ROJO" else R).append(
        f"Score propio con Gini fuera de tiempo de {pct(sc.metricas['Fuera de tiempo']['gini'])}: la entidad "
        f"puede ordenar el riesgo de sus solicitudes.")
    if est.get("ICV_30") in ("ROJO", "ÁMBAR") or est.get("ICV_90") in ("ROJO", "ÁMBAR"):
        R.append(f"Mora creciente: ICV a 30 días de {pct(foto['icv30'])} (desde {pct(ev['icv30'].iloc[0])} hace "
                 f"12 meses) e ICV a 90 días de {pct(foto['icv90'])}.")
    else:
        F.append(f"Calidad de cartera dentro de los límites: ICV a 30 días de {pct(foto['icv30'])}.")
    q, v, ref = r["cosecha_mob6"]
    if q and est.get("COSECHA_MOB6") in ("ROJO", "ÁMBAR"):
        R.append(f"Cosechas recientes más débiles: {pct(v)} en mora 30+ a seis meses ({_cosecha_txt(q)}) frente "
                 f"a {pct(ref)} histórico.")
    t = r["estres"]["tabla"]
    if len(t):
        sev = t.sort_values("ecl_adicional").iloc[-1]
        (R if est.get("ESTRES_SEVERO_PAT") in ("ROJO", "ÁMBAR") else F).append(
            f"En estrés severo las provisiones adicionales serían el {pct(sev['pct_patrimonio'])} del patrimonio y la "
            f"cobertura de la deuda bajaría a {num(sev['cobertura_deuda'], 2)} veces.")
    reg = r["entidad"]["prov_registrada"]
    if not np.isnan(reg):
        (F if reg >= r9.ecl else R).append(
            f"Provisión registrada de {millones(reg)} frente a pérdida esperada NIIF 9 de {millones(r9.ecl)}.")
    return F, R
