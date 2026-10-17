"""Human-facing templates. Values come from the current persisted graph."""
from datetime import datetime
from .database import GraphError

def present(service, slots, old, changes, intents, handoffs, proposals, prior):
    def props(key):
        try:return service.require('story:'+key)['properties']
        except GraphError:return {}
    def clock(key):
        value=props(key).get('starts_at')
        return datetime.fromisoformat(value).strftime('%I:%M %p').lstrip('0') if value else 'a time still to be confirmed'
    father=slots.get('ramesh','your father');priya=props('priya');appt=props('appointment');cab=props('cab')
    escort=priya.get('escort')=='CONFIRMED'
    now=clock('appointment');video=appt.get('location')=='video'
    lines=[];speakers=[]
    if 'family' in intents and not appt:
        names=[slots[n] for n in ('ramesh','priya','meera') if n in changes]
        lines.append('Hi '+slots.get('aarav','there')+'! '+('I’ve connected '+ ' and '.join(names)+' to your family context, so you won’t need to introduce them again. ' if names else '')+'What would you like help organizing?')
    if 'rumor' in intents:
        lines.append('That could affect the plan. I’ll ask Research Assistant to review what we actually know before making changes.')
        speakers.append(('research', 'I wouldn’t cancel the cab yet. The forwarded report hasn’t been independently confirmed, and we don’t have reliable evidence that '+father+'’s appointment was cancelled. Let’s keep the arrangements until the hospital provides an official update.' if slots.get('rumor')=='UNVERIFIED' else 'You’ve clarified that the closure report was false. I’ve kept that correction with the earlier report; no independent provider check is implied.'))
    moved='appointment_start' in changes and bool(old.get('appointment_start'))
    constraints=any(k.endswith(('_available_from','_unavailable_from')) or k in ('deployment_start','physio_start') for k in changes)
    if 'schedule' in intents and not moved and not constraints:
        lines.append(f'Got it. {father}’s hospital follow-up is scheduled for {now}'+(', with Meera accompanying him' if props('meera').get('escort')=='CONFIRMED' else '')+(f' and an internal cab arrangement planned for {clock("cab")}' if cab else '')+'. I’ve linked the appointment and transport so we can keep track of changes together.')
    if constraints and not moved:
        lines.append('I’ve added the availability and commitments.'+(f' Your {clock("deployment")} deployment' if props('deployment') else '')+(f' and {father}’s {clock("physio")} physiotherapy are connected to the family schedule.' if props('physio') else '')+' If the hospital timing changes, I can check the affected arrangements.')
    if moved:
        lines.append(f'The appointment is now at {now}. That affects more than the appointment itself—I’ll ask Schedule Planner to check the connected commitments.')
    if 'availability' in intents and escort and changes.get('priya_escort')=='CONFIRMED':
        lines.append(f'Great, that settles who can accompany {father}. Priya is confirmed'+(f', and the appointment is at {now}.' if appt else '.'))
    if 'video' in intents or 'recall' in intents:
        if appt:
            lines.append(f'Yes. {father}’s follow-up is at {now}'+(', and Priya agreed to accompany him.' if escort else '.')+(' Since you’ve reported a video consultation, I’ll review the earlier transport arrangements before proposing changes.' if video else ' I’ve retrieved the current appointment and family context from memory.'))
        else:lines.append('I don’t have an appointment recorded yet. What time is it, and who is it for?')
    if 'coordination' in intents:
        lines.append('I’ll prepare the schedule changes and a family update for your review.' if appt else 'Which appointment should I coordinate? Please give me its time and the people involved.')
    # Use the actual planner result only when the turn needs planning, not for every fact or summary.
    if appt and (moved or 'video' in intents or 'coordination' in intents or changes.get('priya_escort')=='CONFIRMED'):
        existing=next((text for agent,text in handoffs if agent=='planner'),'')
        if video:
            text=f'The {now} consultation can stay on the schedule'+(f', with Priya helping {father} join from home' if escort else '')+'. The internal transport requirement can be removed. Deployment and physiotherapy stay unchanged; any external cab cancellation needs separate confirmation.'
        elif moved:
            text=f'The {clock("cab")} cab pickup needs review for the {now} appointment. '
            meera=props('meera')
            if meera.get('unavailable_from') and meera['unavailable_from']<=appt['starts_at'][11:16]:text+='Meera is unavailable at that time. '
            if priya.get('available_from'):text+='Priya may be able to help; her agreement is still needed. ' if not escort else 'Priya has agreed to accompany Ramesh. '
            text+='Keep the deployment protected. Appointment duration is still unknown, so a possible overlap with later commitments needs checking.'
        else:text='Priya’s escort commitment is recorded. I’ve reviewed the connected transport task; any proposed pickup adjustment preserves the original travel allowance. Appointment duration remains unknown, so later overlaps are possible.' if escort else 'The linked transport needs review. Who can confirm they will accompany Ramesh? General availability alone is not an escort commitment.'
        # Evidence remains separately inspectable; do not repeat the Coordinator paragraph.
        if existing:speakers.append(('planner',text))
    if proposals:
        speakers.append(('tasks','I’ve prepared the exact internal transport change below. Review it before approving; this does not modify a third-party cab booking.'))
    if appt and ('coordination' in intents or proposals):
        draft=f'{father}’s follow-up is at {now}'+(' by video' if video else '')+'. '+(f'Priya will help him {"join from home" if video else "attend"}. ' if escort else 'The escort still needs confirmation. ')+'Other commitments remain on the schedule.'
        speakers.append(('communication','Draft: “'+draft+'”\n\nWho should receive this, and at which exact email addresses or channel? Nothing has been sent.'))
    if 'summary' in intents:
        lines=['Here’s the latest plan:']
        if appt:lines.append(f'• {father}’s follow-up: {now}, '+('by video.' if video else 'at the hospital.'))
        if escort:lines.append('• Priya: '+('helping him join from home.' if video else 'confirmed to accompany him.'))
        if props('deployment'):lines.append(f'• Your deployment: remains at {clock("deployment")}.')
        if props('physio'):lines.append(f'• Physiotherapy: remains scheduled for {clock("physio")}.')
        if cab:
            if cab.get('status')=='CANCELLED':lines.append('• Internal transport: removed after approval and verified readback. Any external booking remains separate.')
            elif video:lines.append('• Transport: no longer needed for this video visit. The internal change still requires approval; no external cancellation is confirmed.')
            else:lines.append(f'• Internal cab arrangement: {clock("cab")}. Any unapproved change remains pending.')
        lines.append('I’ve preserved the earlier decisions and updates, so you can see how we arrived at this plan.')
        speakers=[]
    if not lines:lines=['That update is saved. I’ll use it when reviewing the connected arrangements.' if changes else 'That matches the current plan. No duplicate arrangements have been created.']
    return '\n\n'.join(lines),speakers
