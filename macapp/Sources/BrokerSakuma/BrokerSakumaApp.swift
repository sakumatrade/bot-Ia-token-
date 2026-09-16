import SwiftUI

@main
struct BrokerSakumaApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup("Broker Sakuma", id: "dashboard") {
            DashboardView()
                .environmentObject(appState)
        }
        .windowResizability(.contentSize)

        MenuBarExtra("Broker Sakuma", systemImage: "chart.line.uptrend.xyaxis") {
            MenuBarContentView()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)
    }
}
