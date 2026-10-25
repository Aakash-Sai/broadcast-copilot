import { useMemo, type CSSProperties } from 'react';
import type { MatchFixture } from './contracts';
import { buildScene,eventLabel } from './matchScene';

export function MatchPitch({fixture,clock,playing,speed}:{fixture?:MatchFixture;clock:number;playing:boolean;speed:number}) {
  const scene=useMemo(()=>fixture ? buildScene(fixture,clock) : null,[fixture,clock]);
  const event=scene?.event;
  const flight=Math.max(.14,Math.min(.9,4/Math.max(1,speed)));
  const ballStyle={
    '--from-x':`${scene?.from.x ?? 50}%`,'--from-y':`${scene?.from.y ?? 50}%`,
    '--to-x':`${scene?.to.x ?? 50}%`,'--to-y':`${scene?.to.y ?? 50}%`,
    '--flight':`${flight}s`,
  } as CSSProperties;
  return <div className={`match-scene ${playing ? 'is-playing' : ''}`}>
    <div className="pitch illustrated-pitch" role="img" aria-label={`Illustrative match view. ${scene?.players.length ?? 0} player markers. ${event ? `Last event: ${eventLabel(event)}.` : 'Ready to play.'}`}>
      <svg className="field-lines" viewBox="0 0 1000 600" preserveAspectRatio="none" aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="12" y="12" width="976" height="576" rx="2"/>
          <path d="M 500 12 V 588"/><circle cx="500" cy="300" r="87"/>
          <path d="M12 155 H165 V445 H12 M988 155 H835 V445 H988 M12 225 H72 V375 H12 M988 225 H928 V375 H988"/>
          <path d="M0 266 H12 V334 H0 M1000 266 H988 V334 H1000"/>
          <path d="M165 240 Q205 300 165 360 M835 240 Q795 300 835 360"/>
        </g>
        <g fill="currentColor"><circle cx="500" cy="300" r="3"/><circle cx="115" cy="300" r="3"/><circle cx="885" cy="300" r="3"/></g>
      </svg>
      {fixture?.teams.map((team,i)=><span key={team.team_id} className={`pitch-team pitch-team-${i===0 ? 'left' : 'right'}`}>
        <i className={`team-key team-key-${i}`}/>{team.name}<small>{scene?.shapes[i]}</small>
      </span>)}
      <div className={`pitch-event ${scene?.goal ? 'pitch-goal' : ''}`} key={`caption-${event?.event_id ?? 'start'}`}>
        {event ? <><small>Last event</small>{eventLabel(event)}</> : 'Ready to play'}
      </div>
      {scene?.moving && <svg className={`event-trail trail-${event?.type} ${event?.outcome==='incomplete' ? 'trail-incomplete' : ''}`} viewBox="0 0 1000 600" preserveAspectRatio="none" aria-hidden="true" key={`trail-${event?.event_id}`}>
        <path d={scene.path}/><circle cx={scene.to.x*10} cy={scene.to.y*6} r="5"/>
      </svg>}
      {scene?.players.map(player=><span key={player.id} className={`pitch-player player-team-${fixture?.teams.findIndex(t=>t.team_id===player.teamId)} ${player.active ? 'player-active' : ''} ${player.goalkeeper ? 'player-keeper' : ''}`}
        style={{left:`${player.x}%`,top:`${player.y}%`}} title={`${player.shirt} · ${player.name}`}>
        {player.shirt}
        {player.active && <span className={`active-player-name ${player.x>76 ? 'name-right' : player.x<24 ? 'name-left' : ''}`}>{player.name}</span>}
      </span>)}
      <span key={`ball-${event?.event_id ?? 'start'}`} className={`match-ball ${scene?.moving ? 'ball-travelling' : ''}`} style={ballStyle} aria-hidden="true"/>
      {scene?.goal && <span className={`goal-glow goal-glow-${scene.teamIndex}`} key={`goal-${event?.event_id}`} aria-hidden="true"/>}
    </div>
    <div className="pitch-disclosure">Illustrative player positions and paths · not live tracking</div>
  </div>;
}
