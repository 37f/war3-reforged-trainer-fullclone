#ifndef WAR3_NATIVE_UNASSIGNED_TEAM_H
#define WAR3_NATIVE_UNASSIGNED_TEAM_H

/* R19.3: explicit -1 tag; never alias it to the valid six-bit team 63. */
#define WAR3_UNASSIGNED_TEAM_TAG (1ULL << 36u)

static uint64_t war3_team_pack_unassigned_peer(const War3TeamPeerSnapshot *source) {
    War3TeamPeerSnapshot value = *source;
    if (value.team < -1 || value.team >= 64) return 0;
    if (value.team == -1) {
        value.team = 0;
        return war3_team_pack(&value) | WAR3_UNASSIGNED_TEAM_TAG;
    }
    return war3_team_pack(&value);
}

static int war3_team_unpack_unassigned_peer(uint64_t packed, War3TeamPeerSnapshot *value) {
    int unassigned = !!(packed & WAR3_UNASSIGNED_TEAM_TAG);
    if ((packed >> 37u) || (unassigned && ((packed >> 12u) & 0x3fu))) return 0;
    if (!war3_team_unpack(packed & ~WAR3_UNASSIGNED_TEAM_TAG, value)) return 0;
    if (unassigned) value->team = -1;
    return 1;
}
#endif
