import test from 'node:test';
import assert from 'node:assert/strict';
import { Euler, Vector3 } from 'three';
import { IFC_VIEW_ROTATION } from '../src/apps/bim-calculator/bim-view.ts';

test('IFC vertical walls remain vertical in the viewer and preserve distances', () => {
  const rotation = new Euler(...IFC_VIEW_ROTATION);
  const bottom = new Vector3(0, 0, 0).applyEuler(rotation);
  const top = new Vector3(0, 0, 3).applyEuler(rotation);
  assert.ok(Math.abs(top.y - bottom.y - 3) < 1e-10, 'A three metre IFC wall must rise three metres on the screen vertical axis');
  assert.ok(Math.abs(top.z - bottom.z) < 1e-10);
  const corner = new Vector3(4, .2, 3);
  const originalDistance = corner.length();
  corner.applyEuler(rotation);
  assert.ok(Math.abs(corner.length() - originalDistance) < 1e-10);
  assert.equal(corner.x, 4);
});
