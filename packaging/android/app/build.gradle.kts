plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "org.meriadock.aqorath"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.meriadock.aqorath"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0+aqr015"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
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

chaquopy {
    defaultConfig {
        version = "3.12"
        buildPython("python3.12")
        pip {
            install("../candidate/aqorath-0+aqr015-py3-none-any.whl")
        }
    }
}
