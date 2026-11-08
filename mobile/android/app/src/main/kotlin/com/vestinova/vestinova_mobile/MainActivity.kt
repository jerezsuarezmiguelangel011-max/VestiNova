package com.vestinova.vestinova_mobile

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import com.vestinova.vestinova_mobile.tryon.TryOnFactory

class MainActivity : FlutterActivity() {
    private var permissionResult: MethodChannel.Result? = null
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        flutterEngine.platformViewsController.registry.registerViewFactory("vestinova/tryon", TryOnFactory(this, flutterEngine.dartExecutor.binaryMessenger))
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger,"vestinova/tryon_permission").setMethodCallHandler { call, result ->
            when(call.method) {
                "request" -> {
                    if(checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED) result.success("granted")
                    else if(permissionResult!=null) result.error("busy","La solicitud de cámara está pendiente.",null)
                    else { permissionResult=result; requestPermissions(arrayOf(Manifest.permission.CAMERA),1818) }
                }
                "settings" -> { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:$packageName")));result.success(null) }
                else -> result.notImplemented()
            }
        }
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode,permissions,grantResults)
        if(requestCode==1818) {
            permissionResult?.success(if(grantResults.firstOrNull()==PackageManager.PERMISSION_GRANTED) "granted"
                else if(shouldShowRequestPermissionRationale(Manifest.permission.CAMERA)) "denied" else "blocked")
            permissionResult=null
        }
    }
    override fun onDestroy() {
        permissionResult?.error("closed","Se cerró la solicitud de cámara.",null);permissionResult=null
        super.onDestroy()
    }
}
