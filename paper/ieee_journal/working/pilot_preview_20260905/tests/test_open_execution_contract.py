"""Regression exposed by the real pilot; currently FAILS, blocking formal runs."""
from test_repairs import parts, envelope
from ds.kernel.clock import Clock

def test_postponed_current_intent_must_not_execute_old_due_party():
    people,hh,world,ix=parts();a=people['a'];clock=Clock(30,2);world.update(clock)
    world.apply_batch(world.resolve_batch([envelope(a,2,3)],clock,7),clock)
    clock.tick();world.update(clock)
    current=envelope(a,3,4)
    outcome=world.apply_batch(world.resolve_batch([current],clock,7),clock)['3:a']
    assert outcome.status != 'executed', 'Current intention says step 4; old step 3 agreement must not override it silently'
