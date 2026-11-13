import test from 'node:test';
import assert from 'node:assert/strict';
import { regionalBounds, observationDate, observationsFromContext, providerStatus } from '../src/apps/tezcatlipoca-hub/intelligence-data.ts';

test('region validation bounds a real query rather than defaulting to a worldwide feed', () => {
  const b = regionalBounds('19.4326', '-99.1332', 100);
  assert.ok(b.latMin < 19.4326 && b.latMax > 19.4326);
  assert.ok(b.lonMin < -99.1332 && b.lonMax > -99.1332);
  assert.ok(b.latMax - b.latMin < 2);
});
test('rejects invalid or boundary-crossing coordinates', () => {
  for (const [lat,lon,r] of [['', '-99', 100], ['91', '-99', 100], ['19','x',100], ['19','-99',500], ['20','179.9',200]]) {
    assert.throws(() => regionalBounds(lat,lon,r));
  }
});
test('does not convert missing or invalid coordinates into zero coordinates', () => {
  const context = {
    earthquakes: [{id:'invalid',lat:null,lon:null,magnitude:null,place:'',time:null,source:'usgs'},
                  {id:'real',lat:19,lon:-99,magnitude:3.3,place:'Puebla',time:'2026-11-11T01:00:00Z',source:'usgs'}],
    aircraft: [{hex:'bad',callsign:'',lat:NaN,lon:-99,source:'adsb_lol',timestamp:null}],
    ships: [{mmsi:'123',name:'Barco',lat:18,lon:-90,source:'ais',timestamp:null}],
  };
  const list = observationsFromContext(context);
  assert.equal(list.length, 2);
  assert.deepEqual(list.map(x => x.kind), ['earthquake','ship']);
  assert.equal(list[1].observedAt, null);
});
test('does not invent timestamps or claim provider availability', () => {
  assert.equal(observationDate(null), null);
  assert.equal(observationDate(''), null);
  assert.equal(providerStatus(undefined,false),'Sin consultar');
  assert.equal(providerStatus({status:'disabled_by_default'},true),'Desactivado por licencia o configuración');
  assert.equal(providerStatus({status:'connected'},true),'Conectado; sin observaciones vigentes');
});
