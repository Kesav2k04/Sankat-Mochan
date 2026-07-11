package com.sankatmochan.mesh.mesh

import com.google.common.truth.Truth.assertThat
import org.junit.Test

class PeerPolicyTest {

    @Test fun `AllowAll admits any address`() {
        assertThat(PeerPolicy.AllowAll.allows("AA:BB:CC:DD:EE:FF")).isTrue()
        assertThat(PeerPolicy.AllowAll.allows("")).isTrue()
    }

    @Test fun `DenyAll refuses every address`() {
        assertThat(PeerPolicy.DenyAll.allows("AA:BB:CC:DD:EE:FF")).isFalse()
    }

    @Test fun `Allowlist matches case-insensitively`() {
        val policy = PeerPolicy.Allowlist(setOf("aa:bb:cc:dd:ee:ff"))
        assertThat(policy.allows("AA:BB:CC:DD:EE:FF")).isTrue()
        assertThat(policy.allows("aa:bb:cc:dd:ee:ff")).isTrue()
    }

    @Test fun `Allowlist rejects addresses not on the list`() {
        val policy = PeerPolicy.Allowlist(setOf("AA:BB:CC:DD:EE:FF"))
        assertThat(policy.allows("11:22:33:44:55:66")).isFalse()
    }

    @Test fun `empty Allowlist rejects everything`() {
        assertThat(PeerPolicy.Allowlist(emptySet()).allows("AA:BB:CC:DD:EE:FF")).isFalse()
    }
}
