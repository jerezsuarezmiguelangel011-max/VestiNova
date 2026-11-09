import java.security.MessageDigest

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Solo activar el complemento con el archivo de Firebase local.
// Así las compilaciones automatizadas sin credenciales/configuración siguen funcionando.
if (file("google-services.json").isFile) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "com.vestinova.vestinova_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.vestinova.vestinova_mobile"
        // La APK de pruebas construida en GitHub se instala al lado de la
        // aplicación local: no reemplaza ni elimina su base SQLite.
        if (System.getenv("VESTINOVA_CI_TEST_APK") == "1") {
            applicationIdSuffix = ".bloque3"
        }
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion // Flutter 3.47 uses API 24; secure storage requires >=23.
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Configure a private release signing key locally before distribution.
    // A production build must never silently use the debug certificate.
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

flutter {
    source = "../.."
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    implementation("com.google.mediapipe:tasks-vision:1.2.2")
    implementation("androidx.camera:camera-core:1.6.2")
    implementation("androidx.camera:camera-camera2:1.6.2")
    implementation("androidx.camera:camera-lifecycle:1.6.2")
}

val verifyPoseModel by tasks.registering {
    val model = layout.projectDirectory.file("src/main/assets/pose_landmarker_lite.task")
    inputs.file(model)
    doLast {
        val bytes = model.asFile.readBytes()
        val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        check(hash == "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a") { "El modelo corporal no coincide con la versión verificada." }
    }
}
tasks.named("preBuild").configure { dependsOn(verifyPoseModel) }
