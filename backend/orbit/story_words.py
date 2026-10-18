"""Deterministic dialogue, formatted from persisted facts, not stage numbers."""
from datetime import datetime
from .database import GraphError
from .story_sources import ARTICLE,TOPIC

def properties(service,key):
    try:return service.require('story:'+key)['properties']
    except GraphError:return {}

def clock(service,key):
    value=properties(service,key).get('starts_at')
    return datetime.fromisoformat(value).strftime('%I:%M %p').lstrip('0') if value else 'time not yet supplied'

def email_draft(service,slots):
    day=slots.get('weekday','the recorded day');when=clock(service,'appointment')
    return f"Dad's {day} hospital appointment",f"Hi Priya,\n\nDad's appointment has moved to {day} at {when}. Thanks for agreeing to take him. I'll confirm the cab arrangements once they're finalized."

def present(service,slots,old,changes,intents,handoffs,proposals,prior,analysis=None):
    appt=properties(service,'appointment');day=slots.get('weekday','the recorded day')
    now=clock(service,'appointment');cab=clock(service,'cab')
    escort=properties(service,'priya').get('escort')=='CONFIRMED'
    moved='appointment_start' in changes and bool(old.get('appointment_start')) and old['appointment_start']!=changes['appointment_start']
    constraints=any(k in changes for k in ('meera_unavailable_from','deployment_start','physio_start'))
    # An introduction is an introduction even if the same graph has prior memory.
    if 'family' in intents and not intents.intersection({'schedule','video','coordination','availability','rumor'}):
        return "I'm sorry to hear about your dad's surgery. I hope he's recovering well.\n\nWhat would you like me to help arrange?",[]
    if 'rumor' in intents:
        return "Let me ask Researcher to check what we actually know.",[('research',f"Let me check the sourced reports.\n\nThe Indian Express references provided:\n{ARTICLE}\n{TOPIC}\n\n[⏳] The Bengaluru protest report could not be retrieved; it is not independently confirmed.\n\n[❌] But {slots.get('destination','The hospital')}'s closure remains unverified." if slots.get('rumor')=='UNVERIFIED' else "[❌] You reported that the closure claim was false. This correction is user-reported, not independently verified.")]
    if 'trip' in intents:
        if slots.get('awaiting_trip')=='yes':return '',[('tasks',"What's the destination?" if not slots.get('destination') else 'Where should the cab pick you up?')]
        return "",[('tasks',"Got the trip details!\n\n[⏳] Uber booking pending — trip details are ready.")]
    if 'video' in intents and appt:
        recalled=(f"Of course, I remember. Dad's appointment was moved to {day} at {now}, and Priya had agreed to take him." if prior and escort else f"Dad's recorded appointment is {day} at {now}." )
        planner=f"Good news! We can simplify the arrangements.\n\n[✅] Dad's appointment remains {day} at {now}, now over video."
        if properties(service,'deployment'):planner+=f"\n[✅] Your {clock(service,'deployment')} team meeting remains scheduled."
        if properties(service,'physio'):planner+=f"\n[✅] Dad's physiotherapy remains scheduled for {clock(service,'physio')}."
        planner+="\n\nThere's just one thing left to review: the earlier cab arrangement."
        return recalled+"\n\nSince it's now a video consultation, let me ask Planner to check what we can simplify.",[('planner',planner),('tasks',"I've made a short to-do list for you.\n\nI'll keep these tasks linked to the updated plan.")]
    if not appt and intents.intersection({'coordination','video','recall'}):
        return "What day and time is Dad's appointment? I need those details before preparing the plan.",[]
    if escort and appt and ('coordination' in intents or changes.get('priya_escort')=='CONFIRMED'):
        subject,body=email_draft(service,slots)
        communication="I've prepared a quick email for Priya.\n\nSubject: "+subject+"\n\n"+body
        if not slots.get('priya_email'):communication+="\n\nWhat's Priya's email address? I'll show the exact approval card before sending."
        else:communication+="\n\nRecipient: "+slots['priya_email']
        return "Perfect, Priya can take over. I'll update the plan and get the message ready for her.",[('planner',f"The updated plan looks good so far.\n\n[✅] Priya will accompany Dad.\n[✅] Hospital appointment: {day}, {now}.\n[⏳] Cab pickup time still needs confirmation."),('communication',communication),('tasks',"[✅] Family schedule updated.\n📧 Waiting for approval to email Priya.\n[⏳] Cab adjustment still pending.")]
    if moved:
        detail=f"I've checked the connected commitments. Here's what needs attention.\n\n[✅] Dad's appointment is now {day} at {now}."
        affected={p['entity_id'] for p in (analysis or {}).get('affected',[])}
        timing=set((analysis or {}).get('timing_review',[]))
        if 'story:cab' in affected:detail+=f"\n[⏳] The {cab} cab pickup needs to be revised."
        if {'story:deployment','story:physio'}<=timing:detail+=f"\n[⏳] Your {clock(service,'deployment')} meeting and Dad's {clock(service,'physio')} physiotherapy need a timing check."
        elif 'story:deployment' in timing:detail+=f"\n[⏳] Your {clock(service,'deployment')} meeting needs a timing check."
        elif 'story:physio' in timing:detail+=f"\n[⏳] Dad's {clock(service,'physio')} physiotherapy needs a timing check."
        return "Absolutely. This changes a few things, so let me ask Planner to review the schedule.",[('planner',detail+"\n\nWe should confirm who can take Dad before changing the transport plan.")]
    if constraints:
        lines=[f"Got it! I've added those commitments to {day}'s plan."]
        if slots.get('meera_unavailable_from'):
            t=datetime.strptime(slots['meera_unavailable_from'],'%H:%M').strftime('%I:%M %p').lstrip('0');lines.append(f"[✅] Your mom is busy after {t}.")
        if properties(service,'deployment'):lines.append(f"[✅] Your team meeting is at {clock(service,'deployment')}.")
        if properties(service,'physio'):lines.append(f"[✅] Dad's physiotherapy is at {clock(service,'physio')}.")
        return "",[('planner',lines[0]+"\n\n"+"\n".join(lines[1:])+"\n\nI'll keep these in mind if anything changes.")]
    if 'schedule' in intents:
        if slots.get('awaiting_trip')=='yes':return "Sure, I'll get Task Manager to help with the transport arrangements.",[('tasks',"Of course! Just need two details.\n\n1. Where should the cab pick you up?\n2. What's the destination?")]
        return f"[✅] Dad's appointment is recorded for {day} at {now}.",[]
    if 'recall' in intents and appt:return f"Dad's recorded appointment is {day} at {now}."+(' Priya has agreed to accompany him.' if escort else ''),[]
    if 'summary' in intents:return f"Here is the recorded plan.\n\n[✅] Hospital appointment: {day}, {now}.\n[⏳] External transport changes require provider confirmation.",[]
    return 'That update is saved. No external action has been executed.',[]
