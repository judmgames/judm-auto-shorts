from judm_auto_shorts.metadata import detect_game,make_metadata

def test_detection():
    assert detect_game('SLIME_run.mp4')=='SLIME'
    assert detect_game('PN37_record.mp4')=='PN37'
    assert detect_game('BLINE_fail.mp4')=='BLINE'
    assert detect_game('FAMMER_battle.mp4')=='FAMMER'

def test_metadata_deterministic():
    assert make_metadata('SLIME_run.mp4')==make_metadata('SLIME_run.mp4')
