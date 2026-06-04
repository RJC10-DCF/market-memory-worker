import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

SOURCE_FILE_NAME = "20260514_Newsrun"

PROMPT = """
Sei un estrattore dati M&A per una banca d'affari.
Leggi la newsrun e restituisci SOLO JSON valido.

Limita l'output ai primi 30 deal della newsrun.

Per ogni deal identifica:
- deal_name
- normalized_deal_name
- description
- industry
- key_financials
- notes
- perimeter
- advisor_name
- normalized_advisor_name
- advisor_role
- process_type
- process_stage
- status
- timing
- seller_or_sponsor
- buyer
- signal_type
- signal_category
- original_text
- confidence

advisor_role ammessi:
sell_side, buy_side, debt_advisor, financial_dd, commercial_dd, legal_dd,
tax_dd, vendor_due_diligence, buyer_due_diligence, restructuring,
strategic_advisor, generic_advisor, unclear

process_stage ammessi:
rumor, beauty_contest, preparation, marketing, due_diligence,
advanced_negotiation, signed_closed, paused, unknown

Regole description:
- description = solo business della target
- non inserire buyer, advisor, stage, esclusività o processo nella description

Regole key_financials:
- estrai ricavi, EBITDA, multipli, metriche finanziarie
- esempio: €160m revenue, €11m EBITDA

Regole advisor multipli:

Se più advisor svolgono lo stesso ruolo:
- associare tutti gli advisor allo stesso ruolo
- non creare advisor sintetici
- non creare valori combinati come:
  "IMI/Cassiopea"
  "Advisor1/Advisor2"
  "Advisor A + Advisor B"

Esempi:

"Cassiopea/IMI advisor sell-side"
→ M&A Advisor Sell-Side = Cassiopea, IMI

"Rothschild e Lazard sell-side advisors"
→ M&A Advisor Sell-Side = Rothschild, Lazard

"Deloitte e PwC svolgono la VDD"
→ VDD Provider = Deloitte, PwC

Regole advisor e banker:

Se il nome di un advisor è seguito tra parentesi dal nome di uno o più banker:

Esempi:
- UBS (Tommaso Poletto)
- Rothschild (Marco De Benedetti)
- Mediobanca (Luca Rossi, Andrea Bianchi)

→ nel campo advisor inserire SOLO il nome della società di advisory:
  UBS
  Rothschild
  Mediobanca

→ i nomi dei banker non devono essere inseriti nei campi advisor.

→ se rilevanti, i nomi dei banker possono essere riportati nelle notes.

Esempio:

"UBS (Tommaso Poletto) incaricata sell-side"

→ M&A Advisor Sell-Side = UBS
→ notes = advisor UBS (Tommaso Poletto)

Regole notes:
- note qualitative o processuali
- esempi: vendita minoranza, one-to-one fallito, focus mercato US, pre-emptive tentato
- notes deve riportare le informazioni qualitative e quantitative rilevanti non già rappresentate bene nelle colonne strutturate.
- notes deve essere ricca ma sintetica.
- includere sempre, se presenti nel testo:
  - revenue / fatturato
  - EBITDA / EBIT
  - NFP / PFN
  - multiplo atteso
  - multiplo pagato
  - valuation / prezzo
  - quota in vendita
  - majority / minority
  - successione / management buy-in
  - buyer interest generico
  - numero di buyer interessati
  - razionale del processo
  - criticità del processo

Esempi:
"€120/130m fatturato; €13.5m EBITDA 2025; vendita maggioranza; ricerca sponsor per il 70%; multiplo atteso 8.0x–8.5x; management buy-in"

"5/6 buyer interessati"

"processo fermo per valuation gap"

REGOLE BUYER, ADVISOR E CONTROPARTI

PRINCIPIO FONDAMENTALE

Una società interessata ad acquistare un asset NON è un advisor.

Distinguere sempre tra:

* Buyer / potenziale acquirente
* M&A Advisor
* DD Provider
* VDD Provider
* Seller / Sponsor

CLASSIFICAZIONE BUYER

Se una società è descritta come:

* interessata all'asset
* interessata all'acquisizione
* potenziale acquirente
* bidder
* offerente
* ha presentato un'offerta
* ha presentato una NBO
* ha presentato una proposta vincolante o non vincolante
* è in shortlist
* sta valutando il dossier
* partecipa al processo
* è tra i soggetti contattati
* è tra gli investitori interessati

ALLORA deve essere classificata come Buyer.

Esempi:

"Peninsula è interessata ad acquisire una quota di minoranza di Rinovha"

→ Buyer = Peninsula

"Apheon ha presentato una NBO"

→ Buyer = Apheon

"Ambienta, Apeiron e Peninsula stanno valutando l'asset"

→ Buyer = Ambienta, Apeiron, Peninsula

"Ricevute offerte da Azimut e Clessidra"

→ Buyer = Azimut, Clessidra

DIVIETO DI CLASSIFICAZIONE ERRATA

Una società identificata come Buyer NON deve MAI essere classificata come:

* M&A Advisor Sell-Side
* M&A Advisor Buy-Side
* DD Provider
* VDD Provider

Esempio ERRATO:

"Peninsula è interessata ad acquisire Rinovha"

→ M&A Advisor Sell-Side = Peninsula

Questo è sbagliato.

GESTIONE DI PIÙ BUYER

Se più soggetti sono interessati allo stesso asset:

Esempio:

"Peninsula, Apheon, Ambienta e Apeiron sono interessati a Rinovha"

Output corretto:

Deal:

* Rinovha

Buyer:

* Peninsula
* Apheon
* Ambienta
* Apeiron

NON creare più deal distinti.

NON duplicare il deal.

Deve esistere un solo deal con più buyer associati.

STAGE DEL PROCESSO

Se esistono buyer nominati che:

* stanno valutando l'asset
* sono stati contattati
* hanno ricevuto il teaser
* hanno espresso interesse
* hanno presentato una NBO
* hanno presentato un'offerta

allora il processo deve essere classificato come:

Stage = Marketing

salvo che il testo indichi chiaramente una fase successiva (Due Diligence, Advanced Negotiation, Signed/Closed).

ADVISOR

Un advisor deve essere identificato solo quando il testo indica chiaramente:

* advisor
* banca incaricata
* sell-side advisor
* buy-side advisor
* financial advisor
* M&A advisor
* banca d'affari
* advisor del venditore
* advisor dell'acquirente

Esempi:

"Rinovha (Xenon): Rothschild sell-side; Peninsula, Apheon, Ambienta e Apeiron interessati"

→ target = Rinovha
→ seller = Xenon
→ M&A Advisor Sell-Side = Rothschild
→ buyer = Peninsula, Apheon, Ambienta, Apeiron
→ creare un solo deal

"UBS advisor buy-side"

→ M&A Advisor Buy-Side = UBS

Se il testo non indica un ruolo di advisor, NON classificare la società come advisor.

Regole perimeter:
- usare solo per perimetro del deal
- esempi: minority stake, majority stake, business SAP only, carve-out
- se non c’è perimetro specifico: null

Regole process_stage:
- probabilmente in vendita / possible exit / stanno pensando all'exit = rumor
- beauty contest / selezione advisor / pitch advisor = beauty_contest
- solo mandato advisor senza altro avanzamento = preparation
- advisor + VDD/FVDD senza teaser out = preparation
- marketing post estate / marketing pre estate / marketing previsto = preparation
- teaser in uscita / IM in preparazione / VDD ongoing / FVDD / CDD / BVDD = preparation
- teaser out / IM out / marketing ongoing / processo live = marketing
- NBO / offerte non vincolanti = marketing
- in esclusiva / one-to-one / bilaterale = due_diligence
- DD buy-side / buyer due diligence = due_diligence
- BO entro / binding offer / offerte vincolanti / binding phase = advanced_negotiation
- signed / signing / closed / closing = signed_closed
- on-hold / fermo / pausato / processo fermo / dead = paused
- se processo fermo dopo esclusiva, prevale paused

Regole advisor:
- mandato sell-side / advisor sell / mandato sell = sell_side
- buy-side / advisor del buyer = buy_side
- buyer in esclusiva = buyer, NON advisor
- PwC/Deloitte/KPMG/EY possono essere M&A advisor o DD provider in base al contesto
- PwC VDD / Deloitte VDD / KPMG FVDD / EY VDD = vendor_due_diligence o financial_dd
- OC&C / Fortlane / BCG / Bain / Roland Berger / RB / Oliver Wyman / OW con VDD/CDD/BVDD = commercial_dd
- KPMG DD buy-side per conto di X = buyer_due_diligence, buyer = X
- se un advisor M&A e un provider DD compaiono nella stessa riga, crea record separati

Regole VDD:
- KPMG, EY, Deloitte, PwC + VDD/FVDD = accounting_vdd
- OC&C, Fortlane, BCG, Bain, Roland Berger/RB, Oliver Wyman/OW + VDD/CDD/BVDD = business_vdd

Regole signal:
- VDD/FVDD/CDD/BVDD/legal VDD/tax VDD = vendor_due_diligence, category diligence
- marketing post estate = marketing_after_summer, category timing
- marketing pre estate = marketing_before_summer, category timing
- teaser out / marketing live = marketing_live, category process
- in esclusiva/one-to-one/bilaterale = exclusivity_granted, category process
- BO entro = binding_phase, category process
- buyer interessati/interesse strategici/PE interessati = buyer_interest, category buyer
- no advisor / advisor non assegnato = advisor_tbd, category advisor
- add-on = add_on_strategy, category shareholder
- pre-emptive = pre_emptive_attempt, category process
- one-to-one fallito = failed_bilateral, category process
- vendita minoranza = minority_sale, category shareholder
- on-hold/fermo = process_paused, category risk
- se non c'è signal chiaro: signal_type = null, signal_category = null

Regole sponsor/buyer:
- testo tra parentesi con “di X” indica spesso sponsor/azionista attuale: seller_or_sponsor = X
- “in passato c’era X” = notes, NON seller_or_sponsor
- buyer/interessata/in esclusiva con/per conto di indica buyer
- non perdere l'informazione tra parentesi

Regole industry:
- classifica ogni deal in UNA SOLA delle seguenti industry:
  FMCG, Industrial, Business Service, Tech, Healthcare, Other

- usa target name, description e notes per inferire l'industry
- se non sei sicuro usa Other

Esempi:
- food, beverage, pane, pasta, consumer goods, caffè = FMCG
- impianti, componentistica, macchinari, packaging, ventilazione, serrature = Industrial
- servizi B2B, testing, outsourcing, HR, compliance, consulenza = Business Service
- software, SAP, Microsoft, IT services, cybersecurity, digital = Tech
- pharma, diagnostics, medical devices, life sciences = Healthcare

Regole stage:
Se il testo contiene:
- "mandato sell"
- "sell-side mandate"
- "advisor incaricato"
- "preparazione teaser"
- "kick-off processo"
- "vendor preparation"

→ process_stage = preparation

Regole target name:
- Il target deve essere solo il nome della società.
- Non includere nel nome target frasi di processo come:
  "in vendita",
  "mandato sell-side",
  "processo in corso",
  "interessata da",
  "di proprietà di".
- Le frasi di processo vanno in notes, stage o seller_or_sponsor.
Esempio:
"Desa in vendita da Azzurra Capital"
→ target = Desa
→ seller_or_sponsor = Azzurra Capital
→ notes = in vendita da Azzurra Capital

Regole stage vs advisor:

Se è presente un advisor sell-side nominato:
→ NON usare Beauty Contest.

In presenza di:
- "mandato sell"
- advisor già incaricato
- advisor nominato
- "sell-side advisor"
- banca incaricata

→ usare almeno:
process_stage = preparation

Beauty Contest va usato solo se:
- l'advisor non è ancora assegnato
- è in corso una selezione advisor
- il testo descrive un advisor bake-off / beauty contest

Regole buyer:
Se un buyer nominato:
- ha fatto un'offerta
- ha presentato una NBO
- è tra le NBO ricevute
- è tra gli offerenti
- ha inviato una proposta
- è in shortlist
- è in fase avanzata
- si è dichiarato interessato o ha mostrato interesse o ha detto che la guarda

→ il buyer deve essere valorizzato nel campo Buyer.

Esempi:

"Azimut ha fatto un'offerta"
→ buyer = Azimut
→ process_stage = marketing

"In arrivo NBO tra cui quella di Azimut"
→ buyer = Azimut
→ process_stage = marketing

"NBO ricevute da Azimut e Clessidra"
→ buyers = Azimut, Clessidra
→ process_stage = marketing

Se viene citato genericamente:
- sponsor finanziario
- private equity
- investitore
- fondo

ma senza nome specifico,
→ NON valorizzare buyer.
Inserire eventualmente l'informazione nelle notes.

Se il testo contiene:
- buyer interessati
- NBO ricevute
- offerte ricevute
- interesse da più sponsor

→ process_stage = marketing

REGOLE BUYER MULTIPLI

Se più buyer sono interessati allo stesso asset/processo:
- creare UN SOLO deal
- NON creare deal separati buyer + target
- il target deve restare la società o asset oggetto del processo
- tutti i buyer interessati devono essere associati allo stesso deal

Esempi:

"Rinovha interessa Peninsula, Apheon, Ambienta e Apeiron"
→ target = Rinovha
→ buyers = Peninsula, Apheon, Ambienta, Apeiron
→ creare un solo deal

"Portfolio company di Xenon che attrae interesse da più sponsor"
→ seller_or_sponsor = Xenon
→ tutti gli sponsor vanno inseriti come buyer dello stesso deal

Non creare nomi sintetici del deal come:
- "Peninsula - Rinovha"
- "Ambienta - Rinovha"
- "Buyer - Target"

a meno che non sia esplicitamente descritto un deal bilaterale firmato.

Output:
- JSON array
- un record per ogni combinazione deal-advisor-ruolo rilevante
- se una riga non ha advisor ma ha un signal importante, crea advisor_name = null
- non inventare dati
- usa confidence high/medium/low
"""

VALID_ADVISOR_ROLES = {
    "sell_side", "buy_side", "debt_advisor", "financial_dd", "commercial_dd",
    "legal_dd", "tax_dd", "vendor_due_diligence", "buyer_due_diligence",
    "restructuring", "strategic_advisor", "generic_advisor", "unclear"
}

VALID_SIGNAL_TYPES = {
    "advisor_mandate",
    "vendor_due_diligence",
    "buyer_interest",
    "possible_exit",
    "minority_sale",
    "exclusivity_granted",
    "binding_phase",
    "process_paused",
    "process_dead",
    "failed_bilateral",
    "pre_emptive_attempt",
    "add_on_strategy",
    "cross_border_m&a",
    "valuation_signal",
    "marketing_before_summer",
    "marketing_after_summer",
    "marketing_live",
    "advisor_tbd",
    "fvdd_started",
    "process_preparation",
    "other"
}

def canonical_name(name):
    if not name:
        return None
    return name.split("(")[0].strip().lower()

def get_source():
    result = (
        supabase.table("sources")
        .select("id,file_name,raw_text,source_date,intelligence_source,source_owner")
        .eq("source_type", "newsrun")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise Exception("No newsrun found in sources")

    return result.data[0]

def extract_json(raw_text):
    response = client.responses.create(
        model="gpt-4.1",
        max_output_tokens=12000,
	input=[
            {"role": "system", "content": "Sei un estrattore dati M&A preciso, conservativo e source-grounded."},
            {"role": "user", "content": PROMPT + "\n\nNEWSRUN:\n" + raw_text}
        ],
    )
    print("OPENAI RAW OUTPUT:")
    print(response.output_text[:2000])

    text = response.output_text.strip()

    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    return json.loads(text)

def upsert_advisor(item):
    name = item.get("advisor_name")
    norm = item.get("normalized_advisor_name")

    if not name or not norm:
        return None

    existing = (
        supabase.table("advisors")
        .select("id")
        .eq("normalized_name", norm)
        .execute()
    )

    if existing.data:
        return existing.data[0]["id"]

    inserted = supabase.table("advisors").insert({
        "name": name,
        "normalized_name": norm,
    }).execute()

    return inserted.data[0]["id"]

def upsert_deal(item, source):
    deal_name = item.get("deal_name")
    normalized = item.get("normalized_deal_name") or canonical_name(deal_name)

    if not deal_name or not normalized:
        return None

    existing = (
        supabase.table("deals")
        .select("id")
        .eq("canonical_name", canonical_name(deal_name))
        .execute()
    )

    if existing.data:
        deal_id = existing.data[0]["id"]

        existing_deal = (
            supabase.table("deals")
            .select("*")
            .eq("id", deal_id)
            .single()
            .execute()
            .data
        )

        def keep_new_or_old(new_value, old_value):
            return new_value if new_value not in [None, ""] else old_value

        supabase.table("deals").update({
            "process_stage": keep_new_or_old(item.get("process_stage"), existing_deal.get("process_stage")),
            "status": keep_new_or_old(item.get("status"), existing_deal.get("status")),
            "timing": keep_new_or_old(item.get("timing"), existing_deal.get("timing")),
            "seller_or_sponsor": keep_new_or_old(item.get("seller_or_sponsor"), existing_deal.get("seller_or_sponsor")),
            "industry": keep_new_or_old(item.get("industry"), existing_deal.get("industry")),
            "description": keep_new_or_old(item.get("description"), existing_deal.get("description")),
            "key_financials": keep_new_or_old(item.get("key_financials"), existing_deal.get("key_financials")),
            "notes": keep_new_or_old(item.get("notes"), existing_deal.get("notes")),
            "perimeter": keep_new_or_old(item.get("perimeter"), existing_deal.get("perimeter")),
            "intelligence_source": source.get("intelligence_source") or source.get("source_owner"),
            "latest_update_date": source.get("source_date"),  
            "uploaded_by": source.get("uploaded_by"),
			"confidence": item.get("confidence") or existing_deal.get("confidence") or "medium",
        }).eq("id", deal_id).execute()

        return deal_id

    inserted = supabase.table("deals").insert({
        "deal_name": deal_name,
        "normalized_deal_name": normalized,
        "canonical_name": canonical_name(deal_name),
        "process_type": item.get("process_type") or "unclear",
        "process_stage": item.get("process_stage") or "unknown",
        "status": item.get("status"),
        "timing": item.get("timing"),
        "industry": item.get("industry"),
        "intelligence_source": source.get("intelligence_source") or source.get("source_owner"),
        "latest_update_date": source.get("source_date"),        
        "seller_or_sponsor": item.get("seller_or_sponsor"),
        "confidence": item.get("confidence") or "medium",
        "uploaded_by": source.get("uploaded_by"),
		"description": item.get("description"),
        "key_financials": item.get("key_financials"),
        "notes": item.get("notes"),
        "perimeter": item.get("perimeter"),
    }).execute()

    return inserted.data[0]["id"]

def insert_deal_advisor(item, deal_id, advisor_id, source_id):
    if not advisor_id or not deal_id:
        return

    role = item.get("advisor_role") or "unclear"
    if role not in VALID_ADVISOR_ROLES:
        role = "unclear"

    existing = (
        supabase.table("deal_advisors")
        .select("id")
        .eq("deal_id", deal_id)
        .eq("advisor_id", advisor_id)
        .eq("role", role)
        .eq("source_id", source_id)
        .execute()
    )

    if existing.data:
        return

    supabase.table("deal_advisors").insert({
        "deal_id": deal_id,
        "advisor_id": advisor_id,
        "role": role,
        "source_id": source_id,
        "original_text": item.get("original_text"),
        "confidence": item.get("confidence") or "medium",
    }).execute()

def insert_signal(item, deal_id):
    signal_type = item.get("signal_type")
    signal_category = item.get("signal_category")

    if not signal_type or not deal_id:
        return

    if signal_type not in VALID_SIGNAL_TYPES:
        signal_type = "other"

    existing = (
        supabase.table("signals")
        .select("id")
        .eq("deal_id", deal_id)
        .eq("signal_type", signal_type)
        .eq("description", item.get("original_text") or "")
        .execute()
    )

    if existing.data:
        return

    supabase.table("signals").insert({
        "signal_type": signal_type,
        "signal_category": signal_category,
        "entity_name": item.get("deal_name"),
        "entity_type": "deal",
        "description": item.get("original_text"),
        "deal_id": deal_id,
        "confidence": item.get("confidence") or "medium",
    }).execute()

def insert_deal_note(item, deal_id, source):
    note_text = item.get("notes")

    if not note_text or not deal_id:
        return

    existing = (
        supabase.table("deal_notes")
        .select("id")
        .eq("deal_id", deal_id)
        .eq("note_text", note_text)
        .execute()
    )

    if existing.data:
        return

    supabase.table("deal_notes").insert({
        "deal_id": deal_id,
        "note_date": source.get("source_date"),
        "source_date": source.get("source_date"),
        "note_text": note_text,
        "source": source.get("intelligence_source") or source.get("source_owner"),
        "uploaded_by": source.get("uploaded_by"),
    }).execute()

def main():
    source = get_source()
    raw_text = source["raw_text"]
    lines = [line for line in raw_text.splitlines() if line.strip()]

    chunk_size = 25
    all_items = []

    print(f"Processing source: {source['file_name']}")
    print(f"Total lines: {len(lines)}")

    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        chunk_text = "\n".join(chunk_lines)

        print(f"Extracting lines {i + 1}-{i + len(chunk_lines)}...")

        try:
            items = extract_json(chunk_text)
            print(f"Extracted {len(items)} records from chunk")

            for item in items:
                deal_id = upsert_deal(item, source)                

                advisor_id = upsert_advisor(item)
                insert_deal_advisor(item, deal_id, advisor_id, source["id"])

                insert_signal(item, deal_id)
                insert_deal_note(item, deal_id, source)

            all_items.extend(items)

        except Exception as e:
            print(f"ERROR processing chunk {i + 1}-{i + len(chunk_lines)}")
            print(e)

    print(f"Total extracted records: {len(all_items)}")    

if __name__ == "__main__":
    main()
