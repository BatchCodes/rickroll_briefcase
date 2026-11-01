plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// CI sets these variables for a release build. A local build uses the
// defaults and the debug key.
val releaseKeystore: String? = System.getenv("BRIEFCASE_KEYSTORE_FILE")
val appVersionName: String = System.getenv("BRIEFCASE_VERSION_NAME") ?: "0.1.0-dev"
val appVersionCode: Int = System.getenv("BRIEFCASE_VERSION_CODE")?.toIntOrNull() ?: 1

android {
    namespace = "io.github.batchcodes.briefcase"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "io.github.batchcodes.briefcase"
        minSdk = 29
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("BRIEFCASE_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("BRIEFCASE_KEY_ALIAS")
                keyPassword = System.getenv("BRIEFCASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (releaseKeystore != null) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    // Android provides org.json at run time. Local unit tests need the real library.
    testImplementation("org.json:json:20240303")
}
