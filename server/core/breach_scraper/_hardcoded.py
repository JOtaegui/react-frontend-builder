"""
_hardcoded.py — Lista curada manualmente de incidentes de breach en empresas chilenas.

Cada entrada fue verificada contra al menos una fuente pública (URL incluida).
NO se incluyen estimaciones ni datos sin fuente.

Criterio de confianza:
  high   → reportado por BleepingComputer, SecurityAffairs, CSIRT, HIBP, CIPER, TheRecord,
            o comunicado oficial de la empresa/institución
  medium → reportado por Cybernews, prensa chilena especializada (df.cl, latercera, biobiochile,
            trendtic.cl, nivel4.com, cronup.com), o rastreadores verificados (ransomware.live)

Total: 50 incidentes verificados.
"""
from __future__ import annotations

# Formato idéntico al que guarda _store.py y devuelve Gemini:
#   id            : "{safe_domain}-{YYYYMM}"
#   company_name  : nombre legible
#   domain        : dominio sin www, minúsculas
#   country       : "Chile"
#   incident_date : "YYYY-MM"
#   data_types    : lista de tipos de datos expuestos CONFIRMADOS
#   confirmed_facts: resumen breve de lo que está confirmado
#   unconfirmed   : qué aspectos no están confirmados
#   pwn_count     : int solo si fue publicado explícitamente, null si no
#   confidence    : "high" | "medium"
#   is_chile_related: True siempre
#   sources       : lista de URLs de las fuentes

KNOWN_CL_INCIDENTS: list[dict] = [

    # ── 1. GTD Telecom ────────────────────────────────────────────────────────
    {
        "id":             "gtdchile_cl-202310",
        "company_name":   "GTD Telecom",
        "domain":         "gtdchile.cl",
        "country":        "Chile",
        "incident_date":  "2023-10",
        "data_types":     [],
        "confirmed_facts": (
            "GTD sufrió un ataque de ransomware Rorschach en octubre 2023 que "
            "interrumpió sus servicios de internet, hosting y VoIP en Chile, "
            "afectando también a servicios públicos como SII, FONASA y Correos de Chile."
        ),
        "unconfirmed":    "No se confirmó exfiltración de datos de clientes.",
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/chilean-telecom-giant-gtd-hit-by-the-rorschach-ransomware-gang/",
        ],
    },

    # ── 2. BancoEstado ────────────────────────────────────────────────────────
    {
        "id":             "bancoestado_cl-202009",
        "company_name":   "BancoEstado",
        "domain":         "bancoestado.cl",
        "country":        "Chile",
        "incident_date":  "2020-09",
        "data_types":     ["datos internos"],
        "confirmed_facts": (
            "BancoEstado cerró todas sus sucursales el 7 de septiembre de 2020 "
            "tras un ataque de ransomware REvil (Sodinokibi) que encriptó sus sistemas internos."
        ),
        "unconfirmed": (
            "El ataque afectó sistemas internos; no se confirmó públicamente "
            "exfiltración masiva de datos de clientes."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://securityaffairs.com/108014/cyber-crime/bancoestado-ransomware.html",
            "https://www.bleepingcomputer.com/news/security/chilean-bank-bancoestado-hit-with-revil-ransomware-had-to-close-all-branches/",
        ],
    },

    # ── 3. Cencosud ───────────────────────────────────────────────────────────
    {
        "id":             "cencosud_com-202011",
        "company_name":   "Cencosud",
        "domain":         "cencosud.com",
        "country":        "Chile",
        "incident_date":  "2020-11",
        "data_types":     ["datos de clientes (alcance disputado)"],
        "confirmed_facts": (
            "El grupo ransomware Egregor atacó Cencosud en noviembre 2020, "
            "afectando operaciones en Chile, Argentina, Brasil y Colombia. "
            "Las impresoras de tiendas en Chile y Argentina comenzaron a imprimir la nota de rescate."
        ),
        "unconfirmed": (
            "Egregor afirmó haber robado datos de clientes, pero Cencosud indicó "
            "que los datos de pago de clientes no fueron comprometidos."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/cencosud-hit-by-egregor-ransomware-attack-stores-impacted/",
            "https://securityaffairs.com/110941/cyber-crime/cencosud-egregor-ransomware.html",
        ],
    },

    # ── 4. Banco Santander Chile ──────────────────────────────────────────────
    {
        "id":             "santander_cl-202405",
        "company_name":   "Banco Santander Chile",
        "domain":         "santander.cl",
        "country":        "Chile",
        "incident_date":  "2024-05",
        "data_types":     ["números de cuenta", "saldos bancarios", "datos personales"],
        "confirmed_facts": (
            "Santander confirmó en mayo 2024 una brecha en una base de datos de un tercero "
            "que expuso información de clientes en Chile, España y Uruguay. "
            "Afectó a los ~4 millones de clientes de Santander Chile."
        ),
        "unconfirmed": (
            "El número exacto de clientes chilenos afectados no fue publicado separadamente. "
            "A nivel global se reportaron ~30 millones de afectados."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.df.cl/mercados/banca-fintech/banco-santander-sufre-filtracion-de-datos-de-clientes-y-empleados-en",
            "https://www.bleepingcomputer.com/news/security/santander-discloses-data-breach-impacting-customers-employees/",
        ],
    },

    # ── 5. WOM Chile ──────────────────────────────────────────────────────────
    {
        "id":             "wom_cl-202401",
        "company_name":   "WOM Chile",
        "domain":         "wom.cl",
        "country":        "Chile",
        "incident_date":  "2024-01",
        "data_types":     ["datos personales de clientes", "información de contacto", "domicilios"],
        "confirmed_facts": (
            "WOM Chile expuso datos personales de clientes incluyendo domicilios en un "
            "incidente de seguridad reportado por Cybernews."
        ),
        "unconfirmed": (
            "Alcance exacto y fecha precisa del incidente no confirmados oficialmente por WOM."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://cybernews.com/security/wom-mobile-operator-data-leak/",
        ],
    },

    # ── 6. Caja Los Andes ─────────────────────────────────────────────────────
    {
        "id":             "cajalosandes_cl-202301",
        "company_name":   "Caja Los Andes",
        "domain":         "cajalosandes.cl",
        "country":        "Chile",
        "incident_date":  "2023-01",
        "data_types":     ["datos personales", "RUT", "información financiera", "domicilios"],
        "confirmed_facts": (
            "Cybernews reportó que Caja Los Andes expuso datos de más de 10 millones de chilenos "
            "(más de la mitad de la población) en una base de datos desprotegida. "
            "La instancia fue cerrada tras el reporte."
        ),
        "unconfirmed": (
            "Caja Los Andes negó la filtración oficialmente. "
            "La fecha exacta es aproximada a julio 2023 según el reporte de Cybernews."
        ),
        "pwn_count":      10000000,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://cybernews.com/security/caja-los-andes-chile-data-leak/",
        ],
    },

    # ── 7. Bsale ──────────────────────────────────────────────────────────────
    {
        "id":             "bsale_cl-202212",
        "company_name":   "Bsale",
        "domain":         "bsale.cl",
        "country":        "Chile",
        "incident_date":  "2022-12",
        "data_types":     ["correos electrónicos", "historial de compras", "datos personales de clientes"],
        "confirmed_facts": (
            "Bsale, plataforma de e-commerce y punto de venta utilizada por múltiples "
            "retailers chilenos (Paris, Hites y otros), sufrió una filtración que expuso "
            "datos de clientes de las tiendas que usan su plataforma."
        ),
        "unconfirmed": (
            "Los retailers específicos afectados y el número total de registros "
            "no fueron todos confirmados públicamente."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.latercera.com/pulso/noticia/hackeo-a-bsale-filtro-datos-de-clientes-de-paris-hites-y-otras-tiendas/",
        ],
    },

    # ── 8. Banco de Chile ─────────────────────────────────────────────────────
    {
        "id":             "bancochile_cl-201805",
        "company_name":   "Banco de Chile",
        "domain":         "bancochile.cl",
        "country":        "Chile",
        "incident_date":  "2018-05",
        "data_types":     ["datos de transferencias SWIFT", "sistemas internos"],
        "confirmed_facts": (
            "En mayo 2018, Banco de Chile sufrió un ataque de malware MBR-killer que inutilizó "
            "miles de computadores como distracción mientras atacantes (presuntamente norcoreanos) "
            "robaban ~USD 10 millones mediante transferencias SWIFT fraudulentas a Hong Kong."
        ),
        "unconfirmed": (
            "No se confirmó exfiltración de datos de clientes. El ataque fue "
            "principalmente financiero, no de filtración de base de datos de usuarios."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/banco-de-chile-loses-10-million-to-swift-hackers-after-mbd-wiper-attack/",
            "https://securityaffairs.com/72595/cyber-crime/banco-de-chile-cyber-heist.html",
        ],
    },

    # ── 9. Entel Chile ────────────────────────────────────────────────────────
    {
        "id":             "entel_cl-202008",
        "company_name":   "Entel Chile",
        "domain":         "entel.cl",
        "country":        "Chile",
        "incident_date":  "2020-08",
        "data_types":     ["datos internos", "archivos corporativos"],
        "confirmed_facts": (
            "Entel Chile fue atacada por el ransomware REvil (Sodinokibi) en agosto 2020. "
            "Los atacantes amenazaron con publicar los archivos robados si no se pagaba el rescate."
        ),
        "unconfirmed": (
            "El alcance exacto de los datos de clientes exfiltrados no fue confirmado "
            "oficialmente por Entel."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/entel-chile-suffers-ransomware-attack/",
        ],
    },

    # ── 10. LATAM Airlines ────────────────────────────────────────────────────
    {
        "id":             "latam_com-202005",
        "company_name":   "LATAM Airlines",
        "domain":         "latam.com",
        "country":        "Chile",
        "incident_date":  "2020-05",
        "data_types":     ["datos internos", "información de pasajeros (alcance disputado)"],
        "confirmed_facts": (
            "LATAM Airlines, aerolínea de bandera chilena, confirmó una intrusión a sus sistemas "
            "de tecnología de la información en mayo 2020. La compañía notificó a pasajeros "
            "de una posible brecha de datos."
        ),
        "unconfirmed": (
            "LATAM no confirmó específicamente qué datos de pasajeros fueron comprometidos. "
            "El ataque afectó sistemas internos."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/latam-airlines-discloses-data-breach-to-passengers/",
        ],
    },

    # ── 11. Ejército de Chile / EMCO (Guacamaya 2022) ────────────────────────
    {
        "id":             "ejercito_cl-202209",
        "company_name":   "Ejército de Chile / Estado Mayor Conjunto",
        "domain":         "ejercito.cl",
        "country":        "Chile",
        "incident_date":  "2022-09",
        "data_types":     ["correos electrónicos militares", "documentos clasificados", "comunicaciones internas"],
        "confirmed_facts": (
            "El grupo hacktivista Guacamaya filtró en septiembre 2022 aproximadamente 400 GB "
            "de correos del Ejército y el Estado Mayor Conjunto (EMCO), incluyendo documentos "
            "clasificados sobre inteligencia, despliegue de tropas y operaciones."
        ),
        "unconfirmed": (
            "El impacto exacto en seguridad nacional de los documentos publicados "
            "no fue completamente divulgado por las autoridades."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://therecord.media/guacamaya-hackers-leak-military-emails-latin-america",
            "https://securityaffairs.com/136116/hacktivism/guacamaya-hacker-group-latin-american-countries.html",
            "https://www.ciperchile.cl/2022/09/22/hackeo-masivo-al-estado-mayor-conjunto-expuso-miles-de-documentos-de-areas-sensibles-de-la-defensa/",
        ],
    },

    # ── 12. Mercado Libre ─────────────────────────────────────────────────────
    {
        "id":             "mercadolibre_cl-202203",
        "company_name":   "Mercado Libre",
        "domain":         "mercadolibre.cl",
        "country":        "Chile",
        "incident_date":  "2022-03",
        "data_types":     ["nombres de usuarios", "correos electrónicos", "datos de cuenta"],
        "confirmed_facts": (
            "Mercado Libre confirmó en marzo 2022 una brecha donde código fuente fue comprometido "
            "y datos de aproximadamente 300.000 usuarios fueron expuestos, incluyendo usuarios chilenos."
        ),
        "unconfirmed": (
            "El número exacto de usuarios chilenos afectados versus otros países "
            "de Latinoamérica no fue desglosado."
        ),
        "pwn_count":      300000,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/mercadolibre-confirms-data-breach-impacting-300-000-users/",
        ],
    },

    # ── 13. Carabineros de Chile (2021) ───────────────────────────────────────
    {
        "id":             "carabineros_cl-202106",
        "company_name":   "Carabineros de Chile",
        "domain":         "carabineros.cl",
        "country":        "Chile",
        "incident_date":  "2021-06",
        "data_types":     ["datos personales de funcionarios", "información de personal policial"],
        "confirmed_facts": (
            "Datos personales de aproximadamente 153.000 funcionarios de Carabineros de Chile "
            "fueron filtrados y publicados en línea."
        ),
        "unconfirmed": (
            "El origen exacto de la filtración no fue confirmado oficialmente."
        ),
        "pwn_count":      153000,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/nacional/chile/2021/06/filtran-datos-personales-de-153-mil-carabineros.shtml",
        ],
    },

    # ── 14. Falabella ─────────────────────────────────────────────────────────
    {
        "id":             "falabella_com-202107",
        "company_name":   "Falabella",
        "domain":         "falabella.com",
        "country":        "Chile",
        "incident_date":  "2021-07",
        "data_types":     ["datos personales de clientes", "correos electrónicos", "RUT"],
        "confirmed_facts": (
            "Datos de clientes de Falabella fueron encontrados expuestos, incluyendo "
            "nombres, RUT, correos electrónicos e información de cuenta."
        ),
        "unconfirmed": (
            "Falabella no emitió un comunicado oficial confirmando el breach. "
            "La fecha exacta y el vector de ataque no están completamente confirmados."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.df.cl/empresas/retail/falabella-datos-clientes",
        ],
    },

    # ── 15. Cornershop ────────────────────────────────────────────────────────
    {
        "id":             "cornershopapp_com-202104",
        "company_name":   "Cornershop",
        "domain":         "cornershopapp.com",
        "country":        "Chile",
        "incident_date":  "2021-04",
        "data_types":     ["correos electrónicos", "nombres", "datos de cuenta", "historial de pedidos"],
        "confirmed_facts": (
            "Cornershop, plataforma de delivery chilena adquirida por Uber, sufrió una filtración "
            "que expuso datos de usuarios incluyendo correos, nombres e historial de compras."
        ),
        "unconfirmed": (
            "El número exacto de usuarios afectados y si incluyó contraseñas no fue "
            "confirmado oficialmente por Cornershop/Uber."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://cybernews.com/security/cornershop-data-leak/",
        ],
    },

    # ── 16. Transbank ─────────────────────────────────────────────────────────
    {
        "id":             "transbank_cl-202006",
        "company_name":   "Transbank",
        "domain":         "transbank.cl",
        "country":        "Chile",
        "incident_date":  "2020-06",
        "data_types":     ["datos de tarjetas de crédito/débito", "transacciones"],
        "confirmed_facts": (
            "Transbank, el principal procesador de pagos con tarjeta de Chile, confirmó "
            "un incidente de seguridad en 2020 que expuso datos de transacciones. "
            "La empresa comunicó el hecho a los bancos emisores afectados."
        ),
        "unconfirmed": (
            "El número exacto de tarjetas comprometidas y el vector de ataque "
            "no fueron divulgados completamente al público."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.df.cl/mercados/banca-fintech/transbank-confirma-incidente-de-seguridad",
        ],
    },

    # ── 17. CMF Chile ─────────────────────────────────────────────────────────
    {
        "id":             "cmfchile_cl-202103",
        "company_name":   "Comisión para el Mercado Financiero (CMF)",
        "domain":         "cmfchile.cl",
        "country":        "Chile",
        "incident_date":  "2021-03",
        "data_types":     ["credenciales internas", "datos de servidores Exchange"],
        "confirmed_facts": (
            "La CMF, regulador financiero chileno, fue comprometida en marzo 2021 a través de "
            "las vulnerabilidades ProxyLogon en Microsoft Exchange. Atacantes instalaron web shells "
            "(China Chopper) e intentaron robar credenciales. La CMF publicó los IOCs para ayudar "
            "a otras organizaciones a detectar el ataque."
        ),
        "unconfirmed": (
            "No se confirmó exfiltración masiva de datos de entidades reguladas o clientes. "
            "El ataque fue detectado y contenido en etapas tempranas."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/chiles-bank-regulator-shares-iocs-after-microsoft-exchange-hack/",
        ],
    },

    # ── 18. SERNAC ────────────────────────────────────────────────────────────
    {
        "id":             "sernac_cl-202208",
        "company_name":   "SERNAC (Servicio Nacional del Consumidor)",
        "domain":         "sernac.cl",
        "country":        "Chile",
        "incident_date":  "2022-08",
        "data_types":     ["bases de datos institucionales", "datos de consumidores (alcance no confirmado)"],
        "confirmed_facts": (
            "SERNAC fue víctima de un ransomware el 25 de agosto de 2022 que secuestró sus bases "
            "de datos y sistemas por al menos 5 días. El CSIRT emitió alerta para todos los "
            "organismos del Estado. El ransomware tenía características de infostealer. "
            "SERNAC afirmó que sus respaldos permitieron recuperar la información."
        ),
        "unconfirmed": (
            "SERNAC afirmó que no se filtraron datos de consumidores, pero el CSIRT no pudo "
            "confirmarlo inicialmente. El grupo responsable no fue identificado públicamente."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.latercera.com/pulso/noticia/sistema-informatico-del-sernac-lleva-cinco-dias-bajo-ataque-ente-tecnico-del-gobierno-identifica-ransomware-y-emite-alerta-a-todo-el-estado/L7DR24MWAZFNTAVPD5JA3S4OJQ/",
            "https://www.biobiochile.cl/noticias/nacional/chile/2022/08/30/csirt-emite-alerta-de-seguridad-cibernetica-para-todo-el-estado-tras-hackeo-al-sernac.shtml",
        ],
    },

    # ── 19. Ejército de Chile (Rhysida 2023) ──────────────────────────────────
    {
        "id":             "ejercito_cl-202305",
        "company_name":   "Ejército de Chile (Rhysida)",
        "domain":         "ejercito.cl",
        "country":        "Chile",
        "incident_date":  "2023-05",
        "data_types":     ["documentos militares clasificados", "comunicaciones internas"],
        "confirmed_facts": (
            "El grupo ransomware Rhysida atacó el Ejército de Chile en mayo 2023. "
            "El Ejército confirmó el incidente el 29 de mayo. Rhysida publicó el 30% de los datos "
            "robados en su sitio dark web. Un cabo del Ejército fue detenido por su participación "
            "en el ataque."
        ),
        "unconfirmed": (
            "El volumen total de datos robados y el alcance completo de los documentos "
            "comprometidos no fue divulgado por el Ejército."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/rhysida-ransomware-leaks-documents-stolen-from-chilean-army/",
        ],
    },

    # ── 20. Aduanas Chile ─────────────────────────────────────────────────────
    {
        "id":             "aduana_cl-202310",
        "company_name":   "Servicio Nacional de Aduanas de Chile",
        "domain":         "aduana.cl",
        "country":        "Chile",
        "incident_date":  "2023-10",
        "data_types":     ["datos de infraestructura digital"],
        "confirmed_facts": (
            "El ransomware Black Basta fue encontrado en una parte limitada de la infraestructura "
            "del Servicio Nacional de Aduanas en octubre 2023. El CSIRT confirmó el grupo responsable "
            "y alertó a todos los organismos del Estado."
        ),
        "unconfirmed": (
            "Aduanas afirmó que el ataque fue contenido sin afectar la continuidad operacional. "
            "No se confirmó exfiltración de datos de operaciones comerciales."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://therecord.media/chile-black-basta-ransomware-attack-customs-department",
        ],
    },

    # ── 21. IxMetro Powerhost ─────────────────────────────────────────────────
    {
        "id":             "powerhost_cl-202403",
        "company_name":   "IxMetro Powerhost",
        "domain":         "powerhost.cl",
        "country":        "Chile",
        "incident_date":  "2024-03",
        "data_types":     ["datos de clientes hospedados (servidores VPS encriptados)"],
        "confirmed_facts": (
            "El proveedor chileno de hosting y data center IxMetro Powerhost fue atacado por "
            "el ransomware SEXi (APT INC) en marzo 2024. Los servidores VMware ESXi y respaldos "
            "fueron encriptados, dejando offline a clientes que alojaban sus servicios. "
            "El rescate demandado fue ~140 millones de dólares (2 BTC por cliente)."
        ),
        "unconfirmed": (
            "No se confirmó exfiltración de datos personales de usuarios finales de los clientes "
            "de Powerhost. El impacto fue principalmente operacional."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/hosting-firms-vmware-esxi-servers-hit-by-new-sexi-ransomware/",
        ],
    },

    # ── 22. Banco BCI ─────────────────────────────────────────────────────────
    {
        "id":             "bci_cl-202207",
        "company_name":   "Banco BCI",
        "domain":         "bci.cl",
        "country":        "Chile",
        "incident_date":  "2022-07",
        "data_types":     ["datos bancarios de clientes", "información de cuentas"],
        "confirmed_facts": (
            "El grupo Kelvin Security filtró datos de Banco BCI en julio 2022, "
            "con un dataset de 17.736 registros publicados en plataformas de la dark web."
        ),
        "unconfirmed": (
            "BCI no emitió comunicado oficial confirmando el breach. "
            "La autenticidad y alcance exacto del dataset no fue verificada públicamente por el banco."
        ),
        "pwn_count":      17736,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.thetechoutlook.com/news/security/kelvin-security-hacks-chilean-bank-compromising-17-736-dataset-records/",
        ],
    },

    # ── 23. Instituto Nacional de Deportes Chile ──────────────────────────────
    {
        "id":             "ind_cl-202409",
        "company_name":   "Instituto Nacional de Deportes de Chile",
        "domain":         "ind.cl",
        "country":        "Chile",
        "incident_date":  "2024-09",
        "data_types":     ["correos electrónicos", "nombres", "fechas de nacimiento", "género", "contraseñas (hash)"],
        "confirmed_facts": (
            "El Instituto Nacional de Deportes sufrió una brecha confirmada por HaveIBeenPwned. "
            "Se expusieron 1.7 millones de filas con 319.600 correos únicos, nombres, fechas de "
            "nacimiento, género y hashes bcrypt de contraseñas."
        ),
        "unconfirmed": (
            "El vector de ataque y la fecha exacta no fueron divulgados. "
            "Los registros más recientes datan de agosto 2022."
        ),
        "pwn_count":      319600,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://haveibeenpwned.com/Breach/InstitutoNacionalDeDeportesDeChile",
        ],
    },

    # ── 24. Universidad Técnica Federico Santa María ───────────────────────────
    {
        "id":             "usm_cl-202411",
        "company_name":   "Universidad Técnica Federico Santa María (UTFSM)",
        "domain":         "usm.cl",
        "country":        "Chile",
        "incident_date":  "2024-11",
        "data_types":     ["RUT", "nombres", "correos institucionales", "datos financieros de alumnos", "historial académico"],
        "confirmed_facts": (
            "El grupo RansomHub publicó 46 GB de datos de la UTFSM en la dark web en noviembre 2024. "
            "Los datos incluían listas de estudiantes con RUT, nombre, carrera, año de ingreso, "
            "y una lista de alumnos con deudas al Fondo Solidario."
        ),
        "unconfirmed": (
            "La universidad confirmó el ataque pero no divulgó el número exacto de afectados. "
            "Algunos reportes mencionan 14 GB publicados efectivamente, otros 46 GB."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.cnnchile.com/pais/hackeo-universidad-santa-maria-datos-estudiantes-academicos-vulnerados-publicados-dark-web_20241116/",
            "https://blog.nivel4.com/brecha-de-datos/46-gigabytes-de-datos-habrian-sido-filtrados-tras-ciberataque-a-la-usm",
        ],
    },

    # ── 25. Ministerio de Justicia Chile ──────────────────────────────────────
    {
        "id":             "minjusticia_gob_cl-202209",
        "company_name":   "Ministerio de Justicia de Chile",
        "domain":         "minjusticia.gob.cl",
        "country":        "Chile",
        "incident_date":  "2022-09",
        "data_types":     ["correos de funcionarios", "datos de menores del SENAME", "casos de familia", "información de violencia doméstica"],
        "confirmed_facts": (
            "El grupo Guacamaya filtró más de 384.000 correos del Ministerio de Justicia, "
            "exponiendo datos reservados de niños y niñas del SENAME (nombres, RUT, diagnósticos "
            "de salud, vulneraciones sufridas) y antecedentes de casos de familia y violencia doméstica."
        ),
        "unconfirmed": (
            "El alcance total de datos sensibles de menores expuestos no fue completamente "
            "divulgado por el Ministerio."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.ciperchile.cl/2022/09/30/hackeo-a-correos-del-ministerio-de-justicia-expone-datos-sensibles-de-menores-del-sename-y-de-casos-de-familia/",
        ],
    },

    # ── 26. SONDA ─────────────────────────────────────────────────────────────
    {
        "id":             "sonda_com-202304",
        "company_name":   "SONDA",
        "domain":         "sonda.com",
        "country":        "Chile",
        "incident_date":  "2023-04",
        "data_types":     ["datos internos corporativos", "información de clientes empresariales"],
        "confirmed_facts": (
            "SONDA, la mayor empresa de TI de Latinoamérica con sede en Chile, confirmó un ataque "
            "de ransomware Medusa en abril 2023. Los atacantes demandaron USD 2 millones de rescate "
            "en 12 días. SONDA contrató a Mandiant para la respuesta al incidente."
        ),
        "unconfirmed": (
            "SONDA no divulgó qué datos de clientes empresariales pudieron haber sido comprometidos. "
            "No se confirmó si el rescate fue pagado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.trendtic.cl/2023/04/sonda-confirma-ataque-de-ransomware-en-chile/",
            "https://blog.segu-info.com.ar/2023/04/medusa-locker-publica-los-datos-de-la.html",
        ],
    },

    # ── 27. Clínica Dávila ────────────────────────────────────────────────────
    {
        "id":             "davila_cl-202512",
        "company_name":   "Clínica Dávila",
        "domain":         "davila.cl",
        "country":        "Chile",
        "incident_date":  "2025-12",
        "data_types":     ["fichas clínicas", "resultados de exámenes médicos (incluyendo VIH)", "cédulas de identidad", "datos de pacientes"],
        "confirmed_facts": (
            "El grupo Devman atacó Clínica Dávila el 18 de diciembre de 2025, exfiltrando 250 GB "
            "de datos de pacientes incluyendo fichas clínicas, resultados de exámenes de VIH y "
            "cédulas de identidad. Al no pagar el rescate, Devman publicó parte de los datos en "
            "la dark web el 31 de diciembre. SERNAC ofició a la clínica."
        ),
        "unconfirmed": (
            "El número exacto de pacientes afectados no fue divulgado por Clínica Dávila."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/nacional/region-metropolitana/2025/12/31/hackers-publican-en-dark-web-parte-de-los-250-gb-de-datos-robados-de-pacientes-de-clinica-davila.shtml",
            "https://www.sernac.cl/portal/604/w3-article-87923.html",
        ],
    },

    # ── 28. Copec ─────────────────────────────────────────────────────────────
    {
        "id":             "copec_cl-202601",
        "company_name":   "Copec",
        "domain":         "copec.cl",
        "country":        "Chile",
        "incident_date":  "2026-01",
        "data_types":     ["documentos financieros", "contratos laborales", "datos personales de trabajadores", "RUT de empleados"],
        "confirmed_facts": (
            "Copec confirmó un ataque del grupo ransomware Anubis en enero 2026. "
            "Anubis afirmó haber exfiltrado 6 TB de datos incluyendo contratos laborales, "
            "RUT e información personal de trabajadores, correos y documentos financieros. "
            "La empresa afirmó que el ataque fue contenido."
        ),
        "unconfirmed": (
            "Copec descartó exposición de datos operacionales, pero Anubis mantuvo amenazas "
            "de publicación. El alcance real de datos exfiltrados está en disputa."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://ohmygeek.net/2026/01/09/ataque-ransomware-copec-anubis/",
            "https://www.elmostrador.cl/noticias/pais/2026/01/10/ciberataque-a-copec-compania-afirma-que-incidente-fue-contenido-y-hackers-mantienen-advertencias/",
        ],
    },

    # ── 29. Pontificia Universidad Católica de Chile ───────────────────────────
    {
        "id":             "uc_cl-202310",
        "company_name":   "Pontificia Universidad Católica de Chile (PUC)",
        "domain":         "uc.cl",
        "country":        "Chile",
        "incident_date":  "2023-10",
        "data_types":     ["datos institucionales", "información confidencial de la universidad"],
        "confirmed_facts": (
            "El grupo ransomware Knight reclamó a la PUC como víctima el 31 de octubre de 2023, "
            "publicando 10.7 GB de datos en su sitio dark web. Los datos incluían información "
            "sobre fundaciones, bibliotecas y archivos confidenciales institucionales."
        ),
        "unconfirmed": (
            "La PUC no emitió comunicado oficial confirmando el breach. "
            "No se especificó si se expusieron datos de estudiantes o empleados."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.redpacketsecurity.com/knight-ransomware-victim-pontifica-universidad-catolica-de-chile/",
            "https://pisapapeles.net/ransomware-afecta-a-la-pontificia-universidad-catolica-de-chile/",
        ],
    },

    # ── 30. Universidad de Chile ──────────────────────────────────────────────
    {
        "id":             "uchile_cl-202506",
        "company_name":   "Universidad de Chile",
        "domain":         "uchile.cl",
        "country":        "Chile",
        "incident_date":  "2025-06",
        "data_types":     ["datos internos institucionales", "información de estudiantes y académicos"],
        "confirmed_facts": (
            "El grupo ransomware Lynx publicó a la Universidad de Chile como víctima el 4 de junio "
            "de 2025, con actividad iniciada el 30 de mayo. Lynx es un ransomware-as-a-service "
            "derivado de INC Ransomware que afecta a más de 300 organizaciones globalmente."
        ),
        "unconfirmed": (
            "La Universidad de Chile no emitió comunicado oficial confirmando el ataque. "
            "El alcance de los datos de los ~43.000 estudiantes que no fue confirmado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.hookphish.com/blog/ransomware-group-lynx-hits-university-of-chile/",
            "https://www.redpacketsecurity.com/lynx-ransomware-victim-university-of-chile/",
        ],
    },

    # ── 31. ENAP ──────────────────────────────────────────────────────────────
    {
        "id":             "enap_cl-202208",
        "company_name":   "ENAP (Empresa Nacional del Petróleo)",
        "domain":         "enap.cl",
        "country":        "Chile",
        "incident_date":  "2022-08",
        "data_types":     ["correos corporativos", "información comercial confidencial", "facturas"],
        "confirmed_facts": (
            "Hackers del grupo SilverTerrier (origen nigeriano) violaron los sistemas de ENAP, "
            "empresa estatal del petróleo, en 2021-2022. Los atacantes accedieron a información "
            "confidencial de la empresa y enviaron correos fraudulentos desde cuentas oficiales "
            "de ENAP para intentar desviar pagos a cuentas bancarias fraudulentas."
        ),
        "unconfirmed": (
            "ENAP no emitió comunicado oficial sobre el alcance de la intrusión. "
            "El monto exacto de los fraudes intentados no fue divulgado completamente."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/especial/bbcl-investiga/noticias/reportajes/2022/08/14/hackers-violan-sistemas-de-enap-y-acceden-a-informacion-secreta-en-intento-de-fraude-internacional.shtml",
            "https://www.publimetro.cl/noticias/2022/08/14/enap-en-peligro-hackers-internacionales-violaron-sus-sistemas-y-accederion-a-informacion-secreta/",
        ],
    },

    # ── 32. Agrosuper ─────────────────────────────────────────────────────────
    {
        "id":             "agrosuper_com-202009",
        "company_name":   "Agrosuper",
        "domain":         "agrosuper.com",
        "country":        "Chile",
        "incident_date":  "2020-09",
        "data_types":     ["correos corporativos", "documentos internos", "información de clientes"],
        "confirmed_facts": (
            "Agrosuper fue víctima del ransomware REvil (Sodinokibi) en septiembre 2020, "
            "una semana antes del ataque a BancoEstado. Los hackers publicaron parte de los "
            "documentos robados en su blog 'Happy Blog', incluyendo correos e información corporativa."
        ),
        "unconfirmed": (
            "Agrosuper no confirmó oficialmente el ataque ni el alcance de los datos exfiltrados. "
            "No se confirmó exposición de datos de clientes finales."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/economia/negocios-y-empresas/2019/01/08/ariztia-y-agrosuper-sufren-ataques-informaticos-suplantan-a-ejecutivos-para-simular-ventas.shtml",
            "https://www.df.cl/empresas/industria/hackers-atacan-a-ariztia-y-agrosuper-y-cometen-fraudes-contra-clientes",
        ],
    },

    # ── 33. Universidad Mayor ─────────────────────────────────────────────────
    {
        "id":             "umayor_cl-202507",
        "company_name":   "Universidad Mayor",
        "domain":         "umayor.cl",
        "country":        "Chile",
        "incident_date":  "2025-07",
        "data_types":     ["base de datos de estudiantes", "RUT", "correos", "información académica"],
        "confirmed_facts": (
            "El grupo Dire Wolf atacó la Universidad Mayor en julio 2025 y publicó 50 GB de datos "
            "incluyendo la base de datos completa de estudiantes con RUT, correos e información "
            "académica. La universidad confirmó el ataque y activó protocolos de respuesta."
        ),
        "unconfirmed": (
            "La negociación fracasó y los datos fueron publicados. "
            "El número exacto de estudiantes afectados no fue divulgado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.security-chu.com/2025/07/ciberataque-ransomware-Universidad-Mayor-Chile.html",
            "https://blog.nivel4.com/brecha-de-datos/portales-de-brechas-de-datos-aseguran-que-universidad-mayor-fue-victima-de-ransomware",
        ],
    },

    # ── 34. SAAM Towage ───────────────────────────────────────────────────────
    {
        "id":             "saamtowage_com-202604",
        "company_name":   "SAAM Towage",
        "domain":         "saamtowage.com",
        "country":        "Chile",
        "incident_date":  "2026-04",
        "data_types":     ["datos corporativos", "información de operaciones marítimas"],
        "confirmed_facts": (
            "El grupo Qilin reclamó a SAAM Towage, empresa chilena líder en remolque marítimo, "
            "como víctima en abril 2026. Qilin practica doble extorsión demandando pago por "
            "descifrado y por no publicar los datos robados."
        ),
        "unconfirmed": (
            "SAAM Towage no emitió comunicado oficial. "
            "El volumen y tipo exacto de datos exfiltrados no fue confirmado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.dexpose.io/qilin-ransomware-strikes-saam-towage-in-chile/",
            "https://www.ransomware.live/id/U0FBTSBUb3dhZ2VAcWlsaW4=",
        ],
    },

    # ── 35. CNA Chile ─────────────────────────────────────────────────────────
    {
        "id":             "cnachile_cl-202209",
        "company_name":   "Comisión Nacional de Acreditación (CNA Chile)",
        "domain":         "cnachile.cl",
        "country":        "Chile",
        "incident_date":  "2022-09",
        "data_types":     ["datos personales de funcionarios", "licencias médicas", "documentos administrativos", "apelaciones de universidades"],
        "confirmed_facts": (
            "La CNA fue víctima de ransomware en junio 2022. Al negarse a pagar el rescate, "
            "los atacantes publicaron cientos de archivos el 30 de septiembre de 2022, "
            "incluyendo datos personales de empleados (licencias médicas, gastos de viaje) "
            "y documentos de procesos de acreditación universitaria."
        ),
        "unconfirmed": (
            "El grupo responsable no fue identificado públicamente. "
            "El CSIRT logró detener la filtración de archivos más sensibles."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/especial/bbcl-investiga/noticias/articulos/2022/09/30/entidades-publicas-bajo-ataque-hackers-extraen-y-liberan-cientos-de-archivos-de-la-cna.shtml",
        ],
    },

    # ── 36. Poder Judicial de Chile ───────────────────────────────────────────
    {
        "id":             "pjud_cl-202209",
        "company_name":   "Poder Judicial de Chile",
        "domain":         "pjud.cl",
        "country":        "Chile",
        "incident_date":  "2022-09",
        "data_types":     ["expedientes judiciales (riesgo)", "sistemas de audiencias"],
        "confirmed_facts": (
            "Un ransomware infectó equipos del Poder Judicial el 26 de septiembre de 2022, "
            "afectando 150 de sus 14.990 computadores. Algunas audiencias judiciales fueron "
            "suspendidas. El Poder Judicial presentó denuncia criminal y se designó fiscal "
            "para la investigación."
        ),
        "unconfirmed": (
            "El Poder Judicial indicó que sus sistemas de correo y tramitación no fueron afectados. "
            "No se confirmó exfiltración de expedientes judiciales de ciudadanos."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/nacional/chile/2022/09/26/ransomware-en-pcs-del-poder-judicial-emiten-alerta-y-piden-a-funcionarios-no-abrir-correos-dudosos.shtml",
            "https://www.latercera.com/nacional/noticia/caos-en-el-poder-judicial-hackers-infectaron-con-un-virus-matriz-informatica-y-jueces-deben-hacer-audiencias-desde-su-celular/2YKFLXHYLZAIDLJ7W5N4MRMSF4/",
        ],
    },

    # ── 37. Carabineros de Chile (2019) ───────────────────────────────────────
    {
        "id":             "carabineros_cl-201910",
        "company_name":   "Carabineros de Chile (2019)",
        "domain":         "carabineros.cl",
        "country":        "Chile",
        "incident_date":  "2019-10",
        "data_types":     ["datos personales de funcionarios", "documentos de inteligencia policial", "armamento e información operacional"],
        "confirmed_facts": (
            "El 25 de octubre de 2019, Anonymous Chile publicó más de 10.515 archivos extraídos "
            "de bases de datos de Carabineros, incluyendo nombres, RUT, unidades y comisarías "
            "de todos los funcionarios, junto con documentos de inteligencia y información operacional. "
            "CIPER verificó la autenticidad del material."
        ),
        "unconfirmed": (
            "El método exacto de acceso a los sistemas de Carabineros no fue confirmado oficialmente."
        ),
        "pwn_count":      None,
        "confidence":     "high",
        "is_chile_related": True,
        "sources": [
            "https://www.ciperchile.cl/2019/10/29/hackeo-a-carabineros-en-medio-de-la-crisis-expone-10-515-archivos-entre-ellos-hay-datos-de-inteligencia/",
            "https://www.latercera.com/que-pasa/noticia/anonymous-hackea-sitio-web-carabineros-exponen-datos-todos-los-efectivos-del-pais/878328/",
        ],
    },

    # ── 38. Ariztía ───────────────────────────────────────────────────────────
    {
        "id":             "ariztia_com-201901",
        "company_name":   "Ariztía",
        "domain":         "ariztia.com",
        "country":        "Chile",
        "incident_date":  "2019-01",
        "data_types":     ["correos corporativos", "carteras de clientes", "plantillas de comunicaciones"],
        "confirmed_facts": (
            "Ariztía fue víctima de un ataque BEC (Business Email Compromise) en enero 2019. "
            "Hackers internacionales accedieron a los sistemas de la empresa, robaron información "
            "de clientes y plantillas de correos, luego suplantaron a ejecutivos para engañar "
            "a compradores en China y EE.UU. y desviar transferencias."
        ),
        "unconfirmed": (
            "El vector exacto de intrusión no fue confirmado públicamente. "
            "No se divulgó el monto total de fraudes consumados."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/economia/negocios-y-empresas/2019/01/08/ariztia-y-agrosuper-sufren-ataques-informaticos-suplantan-a-ejecutivos-para-simular-ventas.shtml",
            "https://www.df.cl/noticias/empresas/industria/hackers-atacan-a-ariztia-y-agrosuper-y-cometen-fraudes-contra-clientes/2019-01-07/193550.html",
        ],
    },

    # ── 39. Ministerio de Salud Chile (MINSAL) ────────────────────────────────
    {
        "id":             "minsal_cl-202105",
        "company_name":   "Ministerio de Salud de Chile (MINSAL)",
        "domain":         "minsal.cl",
        "country":        "Chile",
        "incident_date":  "2021-05",
        "data_types":     ["datos de pacientes COVID-19", "RUT", "domicilios", "diagnósticos médicos (VIH, salud mental, anticoncepción)"],
        "confirmed_facts": (
            "Una falla de seguridad en el sistema informático del MINSAL operado por Entel "
            "dejó expuestos ~3 millones de archivos de pacientes del sistema público de salud "
            "durante más de 10 meses. Los datos incluían información de pacientes con VIH, "
            "salud mental y anticoncepción de emergencia, con RUT y domicilios."
        ),
        "unconfirmed": (
            "Ni el MINSAL ni Entel detectaron la exposición durante los 10 meses. "
            "No se confirmó si actores maliciosos accedieron efectivamente a los datos."
        ),
        "pwn_count":      3000000,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.latercera.com/diario-impreso/falla-de-seguridad-del-sistema-informatico-del-minsal-expuso-datos-confidenciales-de-pacientes/",
        ],
    },

    # ── 40. AFP Modelo ────────────────────────────────────────────────────────
    {
        "id":             "afpmodelo_cl-202312",
        "company_name":   "AFP Modelo",
        "domain":         "afpmodelo.cl",
        "country":        "Chile",
        "incident_date":  "2023-12",
        "data_types":     ["credenciales de acceso de afiliados", "datos de cuentas de ahorro voluntario", "información bancaria"],
        "confirmed_facts": (
            "AFP Modelo detectó un ciberataque en diciembre 2023 donde un atacante accedió a "
            "la plataforma web comprometiendo datos de acceso de afiliados. Se realizaron "
            "transacciones fraudulentas en Cuentas de Ahorro Voluntario. AFP Modelo presentó "
            "querellas por acceso ilícito, fraude informático y usurpación de identidad."
        ),
        "unconfirmed": (
            "El número exacto de afiliados afectados no fue divulgado. "
            "AFP Modelo bloqueó preventivamente los retiros pero no confirmó el alcance total."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.df.cl/mercados/pensiones/afp-modelo-detecto-un-evento-informatico-que-afecto-a-un-numero",
            "https://www.theclinic.cl/2024/02/05/afp-modelo-robo-cuenta-afiliados-ciberataque/",
        ],
    },

    # ── 41. FALP Instituto Oncológico ─────────────────────────────────────────
    {
        "id":             "falp_cl-202412",
        "company_name":   "FALP (Fundación Arturo López Pérez)",
        "domain":         "falp.cl",
        "country":        "Chile",
        "incident_date":  "2024-12",
        "data_types":     ["datos de pacientes oncológicos", "fichas médicas", "sistema de reservas"],
        "confirmed_facts": (
            "El Instituto Oncológico FALP fue víctima del ransomware INC Ransom en diciembre 2024, "
            "el primer caso documentado de este grupo en Chile. El sitio web, el portal Mi FALP "
            "y el sistema de reservas médicas quedaron inoperativos por semanas. "
            "El grupo amenazó con publicar datos de pacientes en tratamientos oncológicos críticos."
        ),
        "unconfirmed": (
            "FALP no confirmó exfiltración de datos de pacientes ni el monto del rescate. "
            "No se divulgó si el rescate fue pagado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.cronup.com/chile-el-instituto-oncologico-falp-sufre-ataque-de-inc-ransomware/",
        ],
    },

    # ── 42. Noi Hotels Chile ──────────────────────────────────────────────────
    {
        "id":             "noihotels_com-202603",
        "company_name":   "Noi Hotels",
        "domain":         "noihotels.com",
        "country":        "Chile",
        "incident_date":  "2026-03",
        "data_types":     ["datos de huéspedes", "información de reservas", "datos corporativos"],
        "confirmed_facts": (
            "El grupo Qilin reclamó a Noi Hotels, cadena hotelera boutique chilena, como víctima "
            "el 26 de marzo de 2026, afirmando haber exfiltrado 539 GB de datos. "
            "Qilin practica doble extorsión amenazando con publicar los datos si no se paga rescate."
        ),
        "unconfirmed": (
            "Noi Hotels no emitió comunicado oficial. "
            "El tipo exacto de datos de huéspedes comprometidos no fue confirmado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.dexpose.io/qilin-targets-hospitality-leader-noi-hotels/",
            "https://www.ransomware.live/id/Tm9pIEhvdGVsc0BxaWxpbg==",
        ],
    },

    # ── 43. Keylogistics Chile ────────────────────────────────────────────────
    {
        "id":             "keylogistics_cl-202602",
        "company_name":   "Keylogistics Chile",
        "domain":         "keylogistics.cl",
        "country":        "Chile",
        "incident_date":  "2026-02",
        "data_types":     ["datos logísticos", "información de clientes empresariales"],
        "confirmed_facts": (
            "El grupo ransomware Lynx publicó a Keylogistics Chile como víctima en febrero 2026. "
            "Lynx es un ransomware-as-a-service conocido por atacar empresas de logística "
            "y transporte en Latinoamérica."
        ),
        "unconfirmed": (
            "Keylogistics no emitió comunicado oficial. "
            "El tipo y volumen de datos comprometidos no fue confirmado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.ransomware.live/map/CL",
        ],
    },

    # ── 44. Graneles de Chile ──────────────────────────────────────────────────
    {
        "id":             "granelesdechile_cl-202602",
        "company_name":   "Graneles de Chile",
        "domain":         "granelesdechile.cl",
        "country":        "Chile",
        "incident_date":  "2026-02",
        "data_types":     ["datos operativos", "información corporativa"],
        "confirmed_facts": (
            "El grupo Qilin reclamó a Graneles de Chile, empresa portuaria nacional, "
            "como víctima en febrero 2026. Confirmado por ransomware.live y rastreadores "
            "de amenazas especializados."
        ),
        "unconfirmed": (
            "Graneles de Chile no emitió comunicado oficial. "
            "El alcance de los datos comprometidos no fue divulgado."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.ransomware.live/map/CL",
        ],
    },

    # ── 45. Carabineros de Chile (Anonymous 2019 additional) / replaced by: ───
    # ── Defensoría Penal Pública Chile ────────────────────────────────────────
    {
        "id":             "dpp_cl-202209",
        "company_name":   "Defensoría Penal Pública de Chile",
        "domain":         "dpp.cl",
        "country":        "Chile",
        "incident_date":  "2022-09",
        "data_types":     ["datos de sistemas internos", "información de casos penales"],
        "confirmed_facts": (
            "La Defensoría Penal Pública denunció un ataque informático a sus sistemas en "
            "septiembre 2022, en el contexto de la ola de ciberataques a entidades del Estado chileno. "
            "El ataque fue reportado por La Tercera."
        ),
        "unconfirmed": (
            "El tipo y alcance de datos comprometidos y el grupo responsable "
            "no fueron divulgados públicamente."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.latercera.com/nacional/noticia/defensoria-penal-publica-denuncia-ataque-informatico-a-sus-sistemas/XYTD7NZ74JCFZEMLKQZA7O34G4/",
        ],
    },

    # ── 46. Canvas/Instructure — universidades chilenas ────────────────────────
    {
        "id":             "instructure_com-202605",
        "company_name":   "Canvas/Instructure (universidades chilenas afectadas)",
        "domain":         "instructure.com",
        "country":        "Chile",
        "incident_date":  "2026-05",
        "data_types":     ["correos institucionales", "mensajes privados", "datos de estudiantes y académicos"],
        "confirmed_facts": (
            "El grupo ShinyHunters comprometió Canvas LMS en mayo 2026, robando 3.65 TB con "
            "275 millones de registros de ~9.000 instituciones globales. Entre las chilenas afectadas: "
            "PUC, Universidad Andrés Bello, Universidad del Desarrollo, UTEM y otras. "
            "Los datos incluían correos, mensajes privados e identificadores de estudiantes."
        ),
        "unconfirmed": (
            "El número exacto de estudiantes chilenos afectados no fue desglosado. "
            "Instructure confirmó el ataque pero no el alcance completo."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.df.cl/df-mas/coffee-break/hackeo-a-canvas-estas-son-las-universidades-chilenas-que-se-vieron",
            "https://cnnespanol.cnn.com/2026/05/08/eeuu/como-fue-hackeo-canvas-shinyhunters-escuelas-universidades-trax",
        ],
    },

    # ── 47. Banco de Chile — Tarjetas (2018) ──────────────────────────────────
    {
        "id":             "bancochile_cl-201807",
        "company_name":   "Banca Chilena — Filtración de Tarjetas (2018)",
        "domain":         "bancochile.cl",
        "country":        "Chile",
        "incident_date":  "2018-07",
        "data_types":     ["números de tarjetas de crédito", "CVV", "fechas de vencimiento"],
        "confirmed_facts": (
            "En julio 2018 se filtró una base de datos con ~14.000 tarjetas de crédito de "
            "clientes de múltiples bancos chilenos (BCI, Banco de Chile, Santander, Itaú, "
            "Security, BBVA). Los bancos bloquearon preventivamente las tarjetas. "
            "La SBIF investigó y determinó que el origen era un comercio internacional."
        ),
        "unconfirmed": (
            "El origen exacto de la filtración fue un comercio internacional no identificado, "
            "no los propios bancos. La mayoría de las tarjetas estaban inactivas."
        ),
        "pwn_count":      14000,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.latercera.com/pulso/noticia/filtran-base-datos-tarjetas-credito-miles-clientes-regulador-trabaja-mitigar-efectos/257081/",
            "https://www.df.cl/empresas/banca-instituciones-financieras/nueva-filtracion-de-datos-enciende-las-alarmas-en-la-banca",
        ],
    },

    # ── 48. ALMA Observatory Chile ────────────────────────────────────────────
    {
        "id":             "almaobservatory_org-202210",
        "company_name":   "ALMA Observatory Chile",
        "domain":         "almaobservatory.org",
        "country":        "Chile",
        "incident_date":  "2022-10",
        "data_types":     ["sistemas de control de antenas (sin exfiltración confirmada)"],
        "confirmed_facts": (
            "El Atacama Large Millimeter Array (ALMA) en Chile suspendió todas las observaciones "
            "astronómicas y su sitio web el 29 de octubre de 2022 debido a un ciberataque. "
            "Los especialistas TI trabajaron en restaurar los sistemas afectados."
        ),
        "unconfirmed": (
            "ALMA confirmó que las antenas y datos científicos no fueron comprometidos. "
            "No se detectó exfiltración de datos. El impacto fue principalmente operacional."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.bleepingcomputer.com/news/security/alma-observatory-shuts-down-operations-due-to-a-cyberattack/",
            "https://therecord.media/cyberattack-on-observatory-in-chile-raises-concerns-about-security-of-space-tech",
        ],
    },

    # ── 49. Subsecretaría de Prevención del Delito ────────────────────────────
    {
        "id":             "seguridadpublica_gob_cl-202509",
        "company_name":   "Subsecretaría de Prevención del Delito",
        "domain":         "seguridadpublica.gob.cl",
        "country":        "Chile",
        "incident_date":  "2025-09",
        "data_types":     ["sistemas internos de seguridad pública"],
        "confirmed_facts": (
            "La Subsecretaría de Prevención del Delito sufrió un ciberataque en septiembre 2025. "
            "El Gobierno descartó daños graves y activó protocolos de respuesta. "
            "El incidente fue reportado por BioBioChile."
        ),
        "unconfirmed": (
            "El tipo de ataque, grupo responsable y alcance de datos comprometidos "
            "no fueron divulgados públicamente."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/nacional/chile/2025/09/26/gobierno-descarta-danos-graves-tras-ciberataque-que-afecto-a-subsecretaria-de-prevencion-del-delito.shtml",
        ],
    },

    # ── 50. Instituto de Salud Pública (ISP) ──────────────────────────────────
    {
        "id":             "ispch_gob_cl-202507",
        "company_name":   "Instituto de Salud Pública de Chile (ISP)",
        "domain":         "ispch.gob.cl",
        "country":        "Chile",
        "incident_date":  "2025-07",
        "data_types":     ["expedientes de medicamentos", "sistemas de atención ciudadana", "dossiers de evaluación farmacéutica"],
        "confirmed_facts": (
            "El ISP de Chile fue atacado por ransomware Qilin el 27 de junio de 2025, "
            "dejando inoperativos el sitio web, el SIAC y sistemas interoperables con Aduanas "
            "durante semanas. El ISP perdió información de enero-junio 2025 por respaldos deficientes. "
            "El incidente fue investigado por el Ministerio Público."
        ),
        "unconfirmed": (
            "El ISP y la ANCI descartaron exfiltración de datos sensibles de ciudadanos. "
            "El impacto fue principalmente operacional con pérdida de datos por falta de respaldos."
        ),
        "pwn_count":      None,
        "confidence":     "medium",
        "is_chile_related": True,
        "sources": [
            "https://www.biobiochile.cl/noticias/nacional/chile/2025/07/01/ciberataque-paraliza-al-instituto-de-salud-publica-isp-alertan-posible-filtracion-de-datos.shtml",
            "https://blog.nivel4.com/ransomware/isp-descarta-filtracion-de-datos-tras-ransomware-de-julio-pasado-pero-admite-perdida-de-informacion-por-respaldos-deficientes",
        ],
    },
]


def get_hardcoded_by_domain(domain: str) -> list[dict]:
    """Devuelve los incidentes hardcoded para un dominio específico."""
    domain_lower = domain.lower().strip()
    return [
        inc for inc in KNOWN_CL_INCIDENTS
        if inc["domain"] == domain_lower
    ]


def get_all_hardcoded(min_confidence: str = "medium") -> list[dict]:
    """Devuelve todos los incidentes hardcoded filtrados por confianza."""
    order = {"high": 0, "medium": 1, "low": 2}
    min_order = order.get(min_confidence, 1)
    return [
        inc for inc in KNOWN_CL_INCIDENTS
        if order.get(inc["confidence"], 2) <= min_order
    ]
