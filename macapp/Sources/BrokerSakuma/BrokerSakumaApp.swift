import AppKit
import SwiftUI

@main
struct BrokerSakumaApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup("DominusBot", id: "dashboard") {
            DashboardView()
                .environmentObject(appState)
                .onOpenURL { _ in
                    // brokersakuma://open - from the browser dashboard's
                    // "Abrir no aplicativo do Mac" link (Info.plist
                    // registers the scheme). Only reachable at all once
                    // this app has been launched as a real "DominusBot.app"
                    // bundle at least once - see Info.plist's comment on
                    // why `swift run` alone can't register it.
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .windowResizability(.contentSize)

        WindowGroup("Configurações", id: "settings") {
            SettingsView()
                .environmentObject(appState)
        }
        .windowResizability(.contentSize)

        MenuBarExtra("DominusBot", systemImage: "chart.line.uptrend.xyaxis") {
            MenuBarContentView()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)
    }
}
