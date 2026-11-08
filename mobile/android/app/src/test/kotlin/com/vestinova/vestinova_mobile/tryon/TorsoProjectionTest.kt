package com.vestinova.vestinova_mobile.tryon
import org.junit.Assert.*
import org.junit.Test

class TorsoProjectionTest {
    private val torso=floatArrayOf(0.5f,0.25f,0.75f,0.3f,0.25f,0.7f,0.25f)
    private val config=listOf(2.1f,1.35f,0f,0f)
    @Test fun fitsInCameraCoordinatesWithoutStretchingThePng() {
        val p=projectTorso(torso,1000,1000,config)!!
        assertEquals(500f,p.x,.01f);assertEquals(500f,p.y,.01f)
        assertEquals(540f,p.width,.01f);assertEquals(675f,p.height,.01f);assertEquals(0f,p.angle,.01f)
        assertEquals(.8f,p.width/p.height,.0001f)
    }
    @Test fun mirroredShouldersDoNotTurnGarmentUpsideDown() {
        val mirrored=torso.copyOf().apply { this[3]=.7f;this[5]=.3f }
        assertEquals(projectTorso(torso,640,480,config),projectTorso(mirrored,640,480,config))
    }
    @Test fun appliesCalibrationOnlyOnceAndUsesPixelAspectRatio() {
        val tilted=torso.copyOf().apply { this[6]=.35f }
        val first=projectTorso(tilted,1000,500,config)!!
        val second=projectTorso(tilted,1000,500,listOf(1.05f,.675f,.1f,.2f))!!
        assertEquals(first.width/2,second.width,.01f);assertEquals(first.height/2,second.height,.01f)
        assertEquals(first.angle,second.angle,.01f);assertTrue(first.angle>0 && first.angle<45)
        assertTrue(second.x>first.x && second.y>first.y)
    }
    @Test fun rejectsUnusableFramesAndDegenerateGeometry() {
        assertNull(projectTorso(torso,0,100,config))
        assertNull(projectTorso(torso.copyOf().apply { this[0]=Float.NaN },100,100,config))
        assertNull(projectTorso(torso.copyOf().apply { this[2]=this[1] },100,100,config))
    }
    @Test fun rejectsCollapsedShouldersInsteadOfDrawingANarrowStrip() {
        val collapsed=torso.copyOf().apply { this[3]=.48f;this[5]=.52f }
        assertNull(projectTorso(collapsed,1000,1000,config))
    }
    @Test fun preservesDifferentPhotoProportionsAndDoesNotExpandBeyondCalibration() {
        for(aspect in listOf(.6f,.8f,1f,1.8f)) {
            val p=projectTorso(torso,1000,1000,config,aspect)!!
            assertEquals(aspect,p.width/p.height,.0001f)
            assertTrue(p.width<=840.01f && p.height<=675.01f)
        }
        assertNull(projectTorso(torso,1000,1000,config,Float.NaN))
    }
    @Test fun hidesSteepOrIncompletePosesRatherThanRotatingAcrossTheBody() {
        val tilted=torso.copyOf().apply { this[4]=.1f;this[6]=.65f }
        assertNull(projectTorso(tilted,1000,1000,config))
        assertNull(projectTorso(torso.copyOf().apply { this[3]=-.1f },1000,1000,config))
    }
    @Test fun requiresStableFramesAndSmoothsNormalTrackingNoise() {
        val tracker=PlacementSmoother()
        val initial=GarmentPlacement(300f,400f,200f,250f,0f)
        assertNull(tracker.update(initial,100))
        assertNull(tracker.update(initial,170))
        assertEquals(initial,tracker.update(initial,240))
        val smoothed=tracker.update(initial.copy(x=320f,width=210f,height=262.5f),310)!!
        assertTrue(smoothed.x>300f && smoothed.x<320f)
        assertEquals(.8f,smoothed.width/smoothed.height,.0001f)
    }
    @Test fun discardsSizeJumpsAndDoesNotHoldAnImageWhenBodyTrackingIsLost() {
        val tracker=PlacementSmoother()
        val initial=GarmentPlacement(300f,400f,200f,250f,0f)
        tracker.update(initial,100);tracker.update(initial,170);tracker.update(initial,240)
        val jump=initial.copy(width=400f,height=500f)
        assertNull(tracker.update(jump,310))
        assertNull(tracker.update(jump,380))
        assertEquals(jump,tracker.update(jump,450))
        assertNull(tracker.update(null,520))
        assertNull(tracker.update(initial,590))
        tracker.reset()
        assertNull(tracker.update(initial,660))
    }
}
