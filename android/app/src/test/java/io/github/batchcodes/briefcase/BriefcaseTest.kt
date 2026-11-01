package io.github.batchcodes.briefcase

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BriefcaseTest {
    @Test
    fun prefersTheNameWhenItAnswers() {
        val checked = mutableListOf<String>()
        val address = Briefcase.firstReachable { url ->
            checked.add(url)
            true
        }
        assertEquals("http://briefcase.lan", address)
        assertEquals(listOf("http://briefcase.lan/healthz"), checked)
    }

    @Test
    fun usesTheIpAddressWhenTheNameDoesNotAnswer() {
        val address = Briefcase.firstReachable { url -> url.startsWith("http://10.42.0.1") }
        assertEquals("http://10.42.0.1", address)
    }

    @Test
    fun returnsNullWhenNothingAnswers() {
        assertNull(Briefcase.firstReachable { false })
    }

    @Test
    fun findsTheStrongestSignalOfTheNetwork() {
        val results = listOf("Home" to -40, "BRIEFCASE" to -80, "BRIEFCASE" to -55)
        assertEquals(-55, Briefcase.strongestRssi(results, "BRIEFCASE"))
        assertNull(Briefcase.strongestRssi(results, "Other"))
    }

    @Test
    fun groupsSignalLevels() {
        assertEquals(Briefcase.Signal.STRONG, Briefcase.signalFor(-50))
        assertEquals(Briefcase.Signal.MEDIUM, Briefcase.signalFor(-70))
        assertEquals(Briefcase.Signal.WEAK, Briefcase.signalFor(-85))
    }

    @Test
    fun checksPasswords() {
        assertTrue(Briefcase.isValidPassword(""))
        assertTrue(Briefcase.isValidPassword("never-gonna-9"))
        assertFalse(Briefcase.isValidPassword("short"))
        assertFalse(Briefcase.isValidPassword("x".repeat(64)))
    }

    @Test
    fun checksNetworkNames() {
        assertTrue(Briefcase.isValidNetworkName("BRIEFCASE"))
        assertFalse(Briefcase.isValidNetworkName(""))
        assertFalse(Briefcase.isValidNetworkName("x".repeat(33)))
    }
}
