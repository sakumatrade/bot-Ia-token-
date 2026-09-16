import SwiftUI

struct StatusBadge: View {
    let state: SystemState
    let displayMode: DisplayMode

    private var color: Color {
        switch state {
        case .online: return .green
        case .paused: return .yellow
        case .safeHalt: return .orange
        case .emergencyStop: return .red
        case .unknown: return .gray
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(state.friendlyLabel)
                .font(.subheadline.weight(.medium))
            if displayMode == .advanced {
                Text("(\(state.rawValue))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
