"""Check what stats becomes after frontend calculates trendResult.today.score.
   Imitate the computeHealthScore call when records=empty, reminders=empty"""
import sys, os
# Manually import the function via Node subprocess (since utils/healthMetrics.js is JS)
import subprocess
out = subprocess.run([
    'node', '-e', '''
    // Manually copy the algorithm since it's JS
    function computeCoverage(records) { return 0; }
    function computeCompliance(reminders) { return { today: 0 }; }
    function computeActivity(consultations) { return 0; }
    const SCORE_WEIGHTS = { compliance: 0.35, coverage: 0.25, activity: 0.20 };
    const today = (computeCompliance([]).today * SCORE_WEIGHTS.compliance) +
                  (computeCoverage([]) * SCORE_WEIGHTS.coverage) +
                  (computeActivity([]) * SCORE_WEIGHTS.activity);
    console.log('today score:', today);
    console.log('NaN?', Number.isNaN(today));
    console.log('isFinite?', Number.isFinite(today));
    '''
], capture_output=True, text=True)
print(out.stdout)
print('stderr:', out.stderr)
