const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const Module=require('node:module');
const path=require('node:path');
const esbuild=require(require.resolve('esbuild',{paths:[require.resolve('vite')]}));
const compiled=esbuild.buildSync({entryPoints:['frontend/src/matchScene.ts'],bundle:true,platform:'node',format:'cjs',write:false});
const sceneFilename=path.resolve('frontend/src/matchScene.cjs');
const sceneModule=new Module(sceneFilename,module);
sceneModule._compile(compiled.outputFiles[0].text,sceneFilename);
const {buildScene}=sceneModule.exports;
const fixture=JSON.parse(fs.readFileSync('data/live_fixture.json','utf8'));
const minute=n=>n*60000;

test('eleven players per team, bounded positions, deterministic seeking including full time',()=>{
  for(const time of [0,15,35,57.99,58,60,67,69,70,74,78,80,90]){
    const scene=buildScene(fixture,minute(time));
    assert.equal(scene.players.length,22);
    for(const team of fixture.teams) assert.equal(scene.players.filter(p=>p.teamId===team.team_id).length,11);
    for(const p of scene.players) assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=5&&p.x<=95&&p.y>=12&&p.y<=88);
    assert.deepEqual(scene,buildScene(fixture,minute(time)));
  }
});

test('substitutions and formations only appear at their actual time',()=>{
  const before=buildScene(fixture,minute(58)-1),after=buildScene(fixture,minute(58));
  assert.ok(before.players.some(p=>p.id==='n-9'));
  assert.ok(!before.players.some(p=>p.id==='n-12'));
  assert.ok(!after.players.some(p=>p.id==='n-9'));
  assert.ok(after.players.some(p=>p.id==='n-12'));
  assert.equal(before.shapes[0],'4-3-3');
  assert.equal(after.shapes[0],'4-2-3-1');
  assert.equal(buildScene(fixture,minute(70)-1).shapes[1],'4-2-3-1');
  assert.equal(buildScene(fixture,minute(70)).shapes[1],'4-4-2');
  const at60=buildScene(fixture,minute(60));
  assert.ok(at60.players.some(p=>p.id==='r-12'));
  assert.ok(!at60.players.some(p=>p.id==='r-9'));
});

test('substitutes inherit the outgoing player position',()=>{
  const quiet={...fixture,events:[]};
  const before=buildScene(quiet,minute(60)-1).players.find(p=>p.id==='r-9');
  const after=buildScene(quiet,minute(60)).players.find(p=>p.id==='r-12');
  assert.deepEqual([after.x,after.y],[before.x,before.y]);
});

test('every event uses only available locations and the correct actor; passes and shots have trails',()=>{
  assert.equal(buildScene(fixture,0).event,undefined);
  for(const event of fixture.events){
    const scene=buildScene(fixture,event.match_clock_ms);
    assert.ok(scene.event.match_clock_ms<=event.match_clock_ms);
    assert.notEqual(scene.event.x,null);
    assert.notEqual(scene.event.y,null);
    assert.equal(scene.moving,['pass','shot'].includes(scene.event.type));
    assert.ok(!scene.path.includes('NaN'));
    const active=scene.players.filter(p=>p.active);
    assert.ok(active.length<=1);
    if(active.length) assert.equal(active[0].id,scene.event.player_id);
  }
});

test('goals illuminate the scoring end only for a short match interval',()=>{
  const goal=fixture.events.find(e=>e.type==='shot'&&e.outcome==='goal'&&e.player_id==='r-12');
  assert.ok(goal);
  const scene=buildScene(fixture,goal.match_clock_ms);
  assert.equal(scene.goal,true);
  assert.equal(scene.teamIndex,1);
  assert.equal(scene.to.x,1);
  assert.equal(buildScene({...fixture,events:[goal]},goal.match_clock_ms+30001).goal,false);
});

function sceneFor(teamIndex,x,type='pass',outcome='completed'){
  const team=fixture.teams[teamIndex].team_id;
  const actor=fixture.players.filter(p=>p.team_id===team)[8];
  const event={...fixture.events[0],type,outcome,team_id:team,player_id:actor.player_id,x,y:50,forward:true};
  return buildScene({...fixture,events:[event]},event.match_clock_ms);
}
const localX=(player,index)=>index===1 ? 100-player.x : player.x;

test('deep attacks advance support lines for either team while retaining cover and keepers',()=>{
  for(const index of [0,1]){
    const team=fixture.teams[index].team_id;
    const buildup=sceneFor(index,35),attack=sceneFor(index,85);
    const support=attack.players.filter(p=>p.teamId===team&&!p.active&&!p.goalkeeper);
    for(const player of support){
      const earlier=buildup.players.find(p=>p.id===player.id);
      assert.ok(localX(player,index)>localX(earlier,index)+20);
    }
    assert.ok(support.filter(p=>localX(p,index)>70).length>=3);
    assert.ok(support.some(p=>localX(p,index)<60));
    assert.ok(localX(attack.players.find(p=>p.teamId===team&&p.goalkeeper),index)<12);
    const opponent=fixture.teams[1-index].team_id;
    const defenders=attack.players.filter(p=>p.teamId===opponent&&!p.goalkeeper);
    for(const player of defenders){
      const earlier=buildup.players.find(p=>p.id===player.id);
      assert.ok(localX(player,1-index)<localX(earlier,1-index));
    }
  }
});

test('pressure advances the opposing team rather than the pressing actor team',()=>{
  const pressure=sceneFor(0,15,'pressure','applied');
  const equivalentAttack=sceneFor(1,85);
  // Ignore the two event actors, whose actual locations override formation anchors.
  for(const player of pressure.players.filter(p=>!p.active)){
    const other=equivalentAttack.players.find(p=>p.id===player.id);
    if(!other.active) assert.deepEqual([player.x,player.y],[other.x,other.y]);
  }
});
