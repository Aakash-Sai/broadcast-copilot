import type { MatchEvent, MatchFixture } from './contracts';

type Point = {x:number; y:number};
export type ScenePlayer = Point & {id:string; name:string; teamId:string; shirt:string; active:boolean; goalkeeper:boolean};
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));

const formations: Record<string,Point[]> = {
  '4-3-3': [{x:7,y:50},...[18,39,61,82].map(y=>({x:22,y})),...[26,50,74].map(y=>({x:35,y})),...[20,50,80].map(y=>({x:46,y}))],
  '4-2-3-1': [{x:7,y:50},...[18,39,61,82].map(y=>({x:22,y})),...[36,64].map(y=>({x:31,y})),...[22,50,78].map(y=>({x:39,y})),{x:47,y:50}],
  '4-4-2': [{x:7,y:50},...[18,39,61,82].map(y=>({x:22,y})),...[18,39,61,82].map(y=>({x:35,y})),...[36,64].map(y=>({x:47,y}))],
};

export function eventLabel(event: MatchEvent) {
  if(event.type==='shot') return event.outcome==='goal' ? 'Goal' : event.outcome==='saved' ? 'Shot saved' : 'Shot off target';
  if(event.type==='pass') return `${event.forward ? 'Forward pass' : 'Pass'} · ${event.outcome==='completed' ? 'complete' : 'incomplete'}`;
  if(event.type==='pressure') return 'Pressure';
  if(event.type==='tackle') return `Tackle · ${event.outcome}`;
  return event.type.replaceAll('_',' ');
}

/** A deterministic illustration of the current roster and last located event, not tracking. */
export function buildScene(fixture: MatchFixture,clock:number) {
  const at=clamp(clock,0,fixture.duration_ms);
  const rosterClock=Math.min(at,fixture.duration_ms-1);
  const active=new Set(fixture.participation.filter(p=>p.start_match_clock_ms<=rosterClock && rosterClock<p.end_match_clock_ms).map(p=>p.player_id));
  const completedSubs=fixture.substitutions.filter(s=>s.match_clock_ms<=at);
  const shapes=fixture.teams.map(team=>fixture.formations.filter(f=>f.team_id===team.team_id && f.match_clock_ms<=at).at(-1)?.shape ?? '4-3-3');
  let event: MatchEvent | undefined;
  for(let i=fixture.events.length-1;i>=0;i--){
    const candidate=fixture.events[i];
    if(candidate.match_clock_ms<=at && candidate.x!=null && candidate.y!=null){event=candidate;break;}
  }
  const teamIndex=event ? fixture.teams.findIndex(team=>team.team_id===event.team_id) : 0;
  const mirror=(point:Point,index:number):Point=>({x:index===1 ? 100-point.x : point.x,y:point.y});
  const seed=event?.sequence ?? 0;
  const source={x:event?.x ?? 50,y:event?.y ?? 50};
  // Pressure and a lost tackle identify the defending actor, not possession.
  // Convert that event location into the attacking team's direction of play.
  const defendingActor=event?.type==='pressure' || (event?.type==='tackle' && event.outcome==='lost');
  const attackingIndex=defendingActor ? 1-teamIndex : teamIndex;
  const attackBall={x:defendingActor ? 100-source.x : source.x,y:source.y};
  const attackDepth=clamp(attackBall.x-35,0,55);
  let target={...source};
  if(event?.type==='pass') target={x:clamp(source.x+(event.forward ? 14 : Math.sin(seed)*9),5,95),y:clamp(source.y+Math.cos(seed*.7)*13,10,90)};
  if(event?.type==='shot') target={x:event.outcome==='saved' ? 94 : 99,y:event.outcome==='off_target' ? (seed%2 ? 24 : 76) : 50};
  const from=mirror(source,teamIndex),to=mirror(target,teamIndex);
  function slot(id:string,seen=new Set<string>()):number {
    if(seen.has(id)) return 0;
    seen.add(id);
    const sub=completedSubs.find(s=>s.player_on_id===id);
    if(sub) return slot(sub.player_off_id,seen);
    const player=fixture.players.find(p=>p.player_id===id);
    const index=fixture.players.filter(p=>p.team_id===player?.team_id).findIndex(p=>p.player_id===id);
    return clamp(index,0,10);
  }
  const players:ScenePlayer[]=fixture.players.filter(p=>active.has(p.player_id)).map(player=>{
    const index=fixture.teams.findIndex(t=>t.team_id===player.team_id);
    const role=slot(player.player_id);
    const anchor=(formations[shapes[index]] ?? formations['4-3-3'])[role];
    const isActor=event?.player_id===player.player_id;
    let local={...anchor};
    if(event){
      const attacking=index===attackingIndex;
      const defender=role>=1 && role<=4;
      const fullback=role===1 || role===4;
      const midfielder=!defender && anchor.x<39;
      if(role===0){
        // Keepers stay close to goal; the attacking keeper can sweep slightly.
        local.x=attacking ? 7+attackDepth*.07 : 5;
        local.y=50+(attackBall.y-50)*.08;
      }else if(attacking){
        // Keep centre backs behind the attack, release fullbacks and move the
        // midfield/forward lines into supporting positions around the ball.
        const advance=defender ? (fullback ? .65 : .45) : midfielder ? .65 : .72;
        local.x=clamp(anchor.x+8+attackDepth*advance,10,90);
        local.y=fullback ? anchor.y : anchor.y+(attackBall.y-50)*.12;
      }else{
        // Defenders retreat as the opposition progresses and narrow around
        // the ball, while forwards remain higher as an outlet.
        local.x=clamp(anchor.x*.85-attackDepth*(defender ? .16 : .12),10,48);
        local.y=50+(anchor.y-50)*.8+(attackBall.y-50)*.15;
      }
      if(role>0){
        const drift=Math.sin(seed*.43+role)*.8;
        local.x+=drift;
        local.y+=drift;
      }
    }
    let point=mirror(local,index);
    if(isActor) point=from;
    return {id:player.player_id,name:player.name,teamId:player.team_id,
      shirt:String(fixture.players.filter(p=>p.team_id===player.team_id).findIndex(p=>p.player_id===player.player_id)+1),
      x:clamp(point.x,5,95),y:clamp(point.y,12,88),active:isActor,goalkeeper:role===0};
  });
  const moving=event?.type==='pass' || event?.type==='shot';
  const mid={x:(from.x+to.x)/2,y:(from.y+to.y)/2+(moving ? Math.sin(seed)*3 : 0)};
  return {players,event,shapes,from,to,moving,teamIndex,
    path:`M ${from.x*10} ${from.y*6} Q ${mid.x*10} ${mid.y*6} ${to.x*10} ${to.y*6}`,
    goal:event?.type==='shot' && event.outcome==='goal' && at-event.match_clock_ms<=30000};
}
