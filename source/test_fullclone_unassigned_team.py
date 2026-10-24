"""Real C and Python regressions for reversible -1 diplomacy, never a live game."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

import war3_reforged_trainer as module
from test_fullclone_protocol import C_HARNESS


CODEC_HARNESS = r'''
__declspec(dllexport) DWORD ua_codec(int32_t team, uint64_t *out) {
#ifdef WAR3_UNASSIGNED_TEAM_TAG
    War3TeamPeerSnapshot source={0}, decoded={0};
    source.team=team; source.player_index=3;
    source.owner_to_peer_mask=5; source.peer_to_owner_mask=7;
    source.assigned_owner_to_peer_mask=8; source.assigned_peer_to_owner_mask=9;
    out[0]=war3_team_pack_unassigned_peer(&source);
    if(!war3_team_unpack_unassigned_peer(out[0], &decoded))return ERROR_INVALID_DATA;
    out[1]=(uint32_t)decoded.team; out[2]=decoded.player_index;
    out[3]=decoded.owner_to_peer_mask; out[4]=decoded.peer_to_owner_mask;
    return 0;
#else
    (void)team; (void)out; return ERROR_NOT_SUPPORTED;
#endif
}
__declspec(dllexport) DWORD ua_unpack(uint64_t packed) {
#ifdef WAR3_UNASSIGNED_TEAM_TAG
    War3TeamPeerSnapshot decoded;
    return war3_team_unpack_unassigned_peer(packed,&decoded)?0:ERROR_INVALID_DATA;
#else
    (void)packed; return ERROR_NOT_SUPPORTED;
#endif
}
'''


@pytest.fixture(scope="module")
def unassigned_native():
    compiler = shutil.which("clang")
    assert compiler, "Unassigned diplomacy tests require the real SEH compiler"
    with tempfile.TemporaryDirectory(prefix="war3-unassigned-") as folder:
        source = Path(folder) / "unassigned.c"
        helper = Path(__file__).parent / "tools" / "war3_native_helper.c"
        source.write_text(C_HARNESS.replace("HELPER_SOURCE", helper.as_posix())
                          + CODEC_HARNESS, encoding="utf8")
        library = Path(folder) / "unassigned.dll"
        build = subprocess.run([compiler, "-shared", "-O2", "-Wno-microsoft-goto", str(source),
                                "-o", str(library), "-luser32", "-lkernel32"],
                               capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, build.stderr
        native = ctypes.CDLL(str(library))
        native.ua_codec.argtypes = [ctypes.c_int32, ctypes.POINTER(ctypes.c_uint64)]
        native.ua_codec.restype = ctypes.c_uint32
        native.ua_unpack.argtypes = [ctypes.c_uint64]
        native.ua_unpack.restype = ctypes.c_uint32
        yield native
        import _ctypes
        _ctypes.FreeLibrary(native._handle)


@pytest.mark.parametrize("team,field,tag", [(-1, 0, 1 << 36), (0, 0, 0), (63, 63, 0)])
def test_unassigned_peer_roundtrip_distinguishes_minus_one_zero_and_63(unassigned_native, team, field, tag):
    out = (ctypes.c_uint64 * 5)()
    assert unassigned_native.ua_codec(team, out) == 0
    assert out[0] == (5 | (7 << 6) | (field << 12) | (3 << 18)
                      | (8 << 23) | (9 << 29) | (1 << 35) | tag)
    assert tuple(out[1:]) == (team & 0xFFFFFFFF, 3, 5, 7)
    assert module._team_relationships_by_player((out[0],)) == {3: out[0]}


@pytest.mark.parametrize("packed", [1 << 36, (1 << 35) | (1 << 37),
                                    (1 << 35) | (1 << 36) | (1 << 12),
                                    (1 << 35) | (28 << 18)])
def test_peer_tag_rejects_contradictory_or_high_bits(unassigned_native, packed):
    assert unassigned_native.ua_unpack(packed) == 13
    assert module._team_relationships_by_player((packed,)) is None


def test_merge_keeps_first_peer_tag_and_original_masks():
    first = (1 << 35) | (1 << 36) | (3 << 18) | 5 | (7 << 6) | (8 << 23)
    later = (1 << 35) | (3 << 18) | (2 << 12) | 8 | (9 << 29)
    merged = module._merge_player_team_relationship_snapshots((first,), (later,))
    assert merged == ((1 << 35) | (1 << 36) | (3 << 18) | 5 | (7 << 6) | (9 << 29),)
    assert module._team_relationships_by_player((first, first)) is None
