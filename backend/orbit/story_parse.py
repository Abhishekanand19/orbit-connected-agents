"""Small deterministic language boundary for the family scenario, not general AI."""
import re
import unicodedata
from difflib import get_close_matches

NAMES=('aarav','ramesh','priya','meera')
ALIASES={'dad':'ramesh','father':'ramesh','papa':'ramesh','mom':'meera','mother':'meera','mum':'meera','sister':'priya'}
VOCAB=set(NAMES)|{'appointment','hospital','followup','rescheduled','shifted','moved','closure','closed','rumor','rumour','protest','available','unavailable','confirms','confirmed','physiotherapy','deployment','consultation','virtual','online','video','cab','taxi','transport','escort','summary','noon','accompany','coordinate','organize'}
NUMBERS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}

def normalize(text):
    text=unicodedata.normalize('NFKC',text).casefold().replace('’',"'")
    text=re.sub(r'\b(a\.?\s*m\.?|p\.?\s*m\.?)\b',lambda m:re.sub(r'[^apm]','',m[0]),text)
    for phrase,value in {"isn't":"is not","hasn't":"has not","didn't":"did not","can't":"cannot","won't":"will not",'quarter to ten':'9:45','quarter to two':'1:45','half past two':'2:30','one forty five':'1:45','nine forty five':'9:45','twelve thirty':'12:30','two thirty':'2:30','follow-up':'followup','follow up':'followup','midday':'12 pm','noon':'12 pm','physio':'physiotherapy','re scheduled':'rescheduled'}.items():
        text=re.sub(r'\b'+re.escape(phrase)+r'\b',value,text)
    text=re.sub(r'\b('+ '|'.join(NUMBERS)+r')\s+(am|pm)\b',lambda m:str(NUMBERS[m[1]])+' '+m[2],text)
    def correct(m):
        word=m[0]
        if len(word)<5 or word in VOCAB:return word
        matches=get_close_matches(word,VOCAB,n=2,cutoff=.86)
        return matches[0] if len(matches)==1 else word
    text=re.sub(r'[a-z]+',correct,text)
    text=re.sub(r"\b(?:um|uh|erm|okay|ok|well|actually|basically|please|you know|i mean)\b",' ',text)
    return re.sub(r'\s+',' ',text).strip()

def times(text):
    result=[]
    for m in re.finditer(r'(?<![\d:-])(\d{1,2})(?:(?::|\.)(\d{2}))?\s*(am|pm)?\b',text):
        h=int(m[1]);minute=int(m[2] or 0)
        if h>23 or minute>59:continue
        if not m[3] and not m[2]:continue
        if not m[3] and h<=12:
            result.append(None);continue
        if m[3]:h=(h%12)+(12 if m[3]=='pm' else 0)
        result.append(f'{h:02}:{minute:02}')
    return result

def parse(text,slots):
    normalized=normalize(text);facts={};questions=[];intents=set()
    # Role identities need no fabricated personal names.
    names={name for name in NAMES if re.search(r'\b'+name+r'\b',normalized)}
    for name in names:facts[name]=name.title()
    introduction=bool(re.search(r'\b(parents|family|sister|father|dad|papa)\b',normalized) and re.search(r'\b(coming|introduce|my name|i am|i.m|here|surgery|care|is my|name is)\b',normalized) and not re.search(r'\b(appointment|video|physiotherapy|meeting)\b',normalized))
    if introduction:intents.add('family')
    for alias,name in ALIASES.items():
        if re.search(r'\b'+alias+r'\b',normalized) and name not in names and name not in slots:
            facts[name]={'ramesh':'Father','meera':'Mother','priya':'Sister'}[name]
    if 'parents' in normalized:
        for key,label in [('ramesh','Father'),('meera','Mother')]:
            if key not in slots and key not in facts:facts[key]=label
    if re.search(r'\b(team meeting|meeting)\b',normalized):facts['deployment_label']='Team meeting'
    if 'monday' in normalized:facts['weekday']='Monday'
    if 'email' in normalized and re.search(r'\b(priya|sister|her)\b',normalized) and not re.search(r'email from',normalized):
        intents.add('coordination');facts['email_requested']='yes'
    addresses=re.findall(r'[^\s<>@,;]+@[^\s<>@,;]+\.[A-Za-z]{2,}',text)
    if addresses and (slots.get('email_requested') or 'email' in normalized):
        if len(addresses)!=1:questions.append('What is Priya’s single email address?')
        else:facts['priya_email']=addresses[0].rstrip('.');intents.add('coordination')
    route=re.search(r'\bfrom\s+(.+?)\s+to\s+(.+?)[.!?]*$',text,re.I)
    if route and (slots.get('awaiting_trip')=='yes' or 'university' in normalized):
        facts['pickup']=route[1].rstrip(', ');facts['destination']=route[2].rstrip('.!? ');facts['awaiting_trip']='no';intents.add('trip')
        if re.fullmatch(r'manipal\s+hospital[, ]+jay(?:a)?nagar',facts['destination'],re.I):facts['destination']='Manipal Hospital, Jayanagar'
        facts['appointment_location']=facts['destination']
    if slots.get('pending_specialist')=='tasks' and 'trip' not in intents:
        pickup=re.search(r'(?:pick\s*(?:me|us)?\s*up\s+(?:at|from)|pickup(?: is|:)?)\s+(.+)',text,re.I)
        destination=re.search(r'(?:destination(?: is|:)?|take (?:me|us) to)\s+(.+)',text,re.I)
        if pickup or destination:
            if pickup:facts['pickup']=pickup[1].rstrip('.!? ')
            if destination:
                value=destination[1].rstrip('.!? ')
                facts['destination']='Manipal Hospital, Jayanagar' if re.fullmatch(r'manipal\s+hospital[, ]+jay(?:a)?nagar',value,re.I) else value
                facts['appointment_location']=facts['destination']
            facts['awaiting_trip']='no' if all(facts.get(k) or slots.get(k) for k in ('pickup','destination')) else 'yes'
            intents.add('trip')
    if re.search(r'\b(he|his|him)\b',normalized) and 'ramesh' not in slots and 'ramesh' not in facts:
        questions.append('Who does “he” refer to?')
    if re.search(r'\b(he|his|him)\b',normalized) and len(names&{'aarav','ramesh'})>1:
        questions.append('Does “he” refer to Aarav or Ramesh?')
    if any(name not in slots for name in names) and not intents:intents.add('family')
    # Split independent clauses, not entire-message equality checks.
    clauses=re.split(r'[,;!\n]|\.(?!\d)|\band\b|\bbut\b',normalized)
    current=slots.get('focus','appointment' if slots.get('appointment_start') else '')
    last_actor=None
    for clause in clauses:
        mentions=[(m.start(),m[0] if m[0] in NAMES else ALIASES[m[0]]) for m in re.finditer(r'\b('+'|'.join((*NAMES,*ALIASES))+r')\b',clause)]
        actor=mentions[0][1] if mentions else None
        pronoun=re.search(r'\b(she|her)\b',clause)
        if pronoun and (not mentions or pronoun.start()<mentions[0][0]):
            actor=last_actor or slots.get('person_focus')
            if actor not in ('priya','meera'):actor=None;questions.append('Do you mean Meera or Priya?')
        if actor:last_actor=actor
        subject=None
        if re.search(r'\b(cab|taxi|transport|ride|uber)\b',clause):subject='cab'
        elif 'physiotherapy' in clause:subject='physio'
        elif re.search(r'\b(deployment|deploy|release|work|meeting)\b',clause):subject='deployment'
        elif re.search(r'\b(appointment|followup|consultation|visit|slot|timing)\b',clause):subject='appointment'
        elif re.search(r'\b(moved|rescheduled|shifted|postponed)\b',clause):subject=current
        reschedule=bool(re.search(r'\b(moved|rescheduled|shifted|postponed|changed|now|from.+to)\b',clause))
        negated=bool(re.search(r'\b(not|never|no longer)\b.{0,12}\b(moved|rescheduled|shifted|cancelled|canceled)\b',clause))
        raw=list(re.finditer(r'(?<![\d:-])(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',clause))
        t=[]
        for match in raw:
            h=int(match[1]); minute=int(match[2] or 0); meridiem=match[3]
            if h>23 or minute>59:continue
            if not meridiem and h<=12:
                # Resolve a forward reschedule against the stored earlier time.
                anchor=slots.get('appointment_start') if subject=='appointment' and reschedule else None
                if anchor or (subject=='appointment' and reschedule and len(raw)>1):
                    old_hour=int(raw[0][1]) if len(raw)>1 and 'from' in clause else int((anchor or raw[0][1]).split(':')[0])
                    h=min((h%12,h%12+12),key=lambda candidate:abs(candidate-old_hour))
                elif (subject in ('appointment','cab') and re.search(r'\b(cab|taxi)\b',normalized) and re.search(r'\b(appointment|followup)\b',normalized)):
                    h=h%12  # Explicit paired morning appointment / pickup convention.
                elif subject in ('deployment','physio') or actor=='meera' and h==12:
                    h=h%12+12
                else:
                    questions.append('Is that time AM or PM?');t.append(None);continue
            elif meridiem:h=h%12+(12 if meridiem=='pm' else 0)
            t.append(f'{h:02}:{minute:02}')
        if subject:
            current=subject
            if t and all(t) and not negated:
                facts[subject+'_start']=t[-1] if reschedule else t[0];intents.add('schedule')
                if reschedule and len(t)>1:facts[subject+'_previous_reported']=t[0]
                elif len(t)>1:facts[subject+'_end']=t[1]
            elif reschedule and not negated and not t and re.search(r'\b(moved|rescheduled|shifted|postponed|changed)\b',clause):questions.append('What is the new appointment time?')
        if negated:intents.add('recall')
        if actor and re.search(r'\b(free|available|availability|unavailable|busy|cannot|can.t|confirms|confirmed|can escort|can take|can accompany|will accompany|will take|will escort|is taking)\b',clause):
            intents.add('availability')
            negative=bool(re.search(r'\b(unavailable|busy|cannot|can.t|not available|not free|not confirmed|not confirm|no longer available|will not)\b',clause))
            if t and t[0]:facts[actor+('_unavailable_from' if negative else '_available_from')]=t[0]
            elif negative:facts[actor+'_availability']='REFUTED'
            commitment=bool(re.search(r'\b(accompany|escort|take|taking)\b',clause))
            if commitment:facts[actor+'_escort']='PENDING' if re.search(r'\b(not confirmed|not confirm)\b',clause) else 'REFUTED' if negative else 'CONFIRMED'
            if not negative:
                facts[actor+'_availability']='CONFIRMED' if re.search(r'\b(confirms|confirmed|definitely|can escort|can take|can accompany|will accompany|will take|will escort|is taking|yes)\b',clause) else 'PENDING'
        if re.search(r'\b(video|online|virtual|remote)\b',clause) and not re.search(r'\b(not|no longer)\b.{0,12}\b(video|online|virtual|remote)\b',clause) and (subject=='appointment' or slots.get('appointment_start')):
            intents.add('video');facts['appointment_location']='video'
        if (re.search(r'\b(hospital|clinic)\b',clause) or (slots.get('appointment_start') and subject in (None,'appointment'))) and re.search(r'\b(closed|closure|protest|rumor|rumour|shut)\b',clause):
            intents.add('rumor');facts['rumor']='REFUTED' if re.search(r'\b(not closed|no closure|false|untrue)\b',clause) else 'UNVERIFIED'
        if 'physiotherapy' in clause and re.search(r'\b(done|completed|finished)\b',clause):facts['physio_status']='DONE'
    if last_actor:facts['person_focus']=last_actor
    if 'rumor' in intents and 'protest' in normalized:facts['protest']='UNVERIFIED'
    if 'rumor' in intents and 'whatsapp' in normalized:facts['rumor_source']='WhatsApp message reported by user'
    if 'tomorrow' in normalized:facts['day_offset']='1'
    if re.search(r'\b(coordinate|organize|organise|arrange everything|tell everyone|notify|family update|keep everyone|sort.*out)\b',normalized):intents.add('coordination')
    if re.search(r'\b(remember|recall|remind)\b',normalized):intents.add('recall')
    if re.search(r'\b(summary|summarize|summarise|recap|wrap up|final state|where.*stand|what.*changed|all set)\b',normalized):intents.add('summary')
    if re.search(r'\b(email|send|notify|message|tell)\b',normalized) and not intents:questions.append('Which exact recipient or channel and content should be prepared for approval?')
    if not intents and not questions:questions.append('Tell me who is involved and what changed—an appointment time, availability, transport, or a request for a summary.')
    if 'rumor' in intents and not (names or slots.get('ramesh') or slots.get('appointment_start') or facts.get('appointment_start')):
        questions.append('Whose hospital appointment does this report concern?')
    if facts.get('cab_start') and not slots.get('pickup') and not facts.get('pickup'):facts['awaiting_trip']='yes'
    if current:facts['focus']=current
    combined={**slots,**facts}
    for key in ('appointment','cab','physio','deployment'):
        if combined.get(key+'_start') and combined.get(key+'_end') and combined[key+'_end']<=combined[key+'_start']:
            questions.append('What is the end time? It must be later than the start time on the demo day.')
    # Ambiguous input is never partially applied.
    return {'facts':facts,'intents':sorted(intents),'questions':list(dict.fromkeys(questions)),'normalized':normalized}
