import SwiftUI

/// Minimal settings screen so the app can actually authenticate to the
/// Local API — this was missing entirely until now (the Local API's
/// authentication was built after this app's first pass, and nothing
/// ever threaded a key through). The key is stored in `UserDefaults`
/// (via `AppState.apiKey`'s `didSet`), never in code, git, or logs.
struct SettingsView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Configurações").font(.title2.bold())

            VStack(alignment: .leading, spacing: 6) {
                Text("Chave da API").font(.subheadline.weight(.medium))
                SecureField("Cole a chave aqui", text: $appState.apiKey)
                    .textFieldStyle(.roundedBorder)
                Text(
                    "Esta é a mesma chave configurada no backend "
                    + "(variável de ambiente BROKER_SAKUMA_LOCAL_API__API_KEY). "
                    + "Nunca é uma frase de recuperação ou chave privada de carteira."
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Text("Endereço da API Local: http://127.0.0.1:8765 (padrão)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .frame(width: 380)
    }
}
