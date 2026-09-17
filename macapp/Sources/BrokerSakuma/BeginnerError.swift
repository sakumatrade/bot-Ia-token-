import Foundation

/// Errors the API client can raise. Kept small and specific so
/// `BeginnerMessage` can map each one to a plain-language explanation
/// instead of ever showing a raw status code to a non-technical user
/// (spec section 43).
enum APIError: Error, Equatable {
    case notConnected
    case serverError(statusCode: Int)
    case decodingFailed
    case unauthorized
    case missingAPIKey
}

/// Spec section 43: never show "HTTP 500" by default. Show a plain
/// sentence, and hide the technical detail behind an explicit
/// "Ver detalhes técnicos" toggle in the UI.
enum BeginnerMessage {
    struct Presentation {
        let headline: String
        let technicalDetails: String
    }

    static func present(_ error: Error) -> Presentation {
        switch error {
        case APIError.notConnected:
            return Presentation(
                headline: "O DominusBot não conseguiu se conectar ao sistema agora.",
                technicalDetails: "notConnected: nenhuma resposta da API local (verifique se o backend está rodando)."
            )
        case APIError.serverError(let statusCode):
            return Presentation(
                headline: "O DominusBot não conseguiu consultar a informação agora.",
                technicalDetails: "HTTP \(statusCode)"
            )
        case APIError.decodingFailed:
            return Presentation(
                headline: "O DominusBot recebeu uma resposta que não entendeu.",
                technicalDetails: "decodingFailed: o formato da resposta não bateu com o esperado."
            )
        case APIError.unauthorized:
            return Presentation(
                headline: "A chave da API configurada está incorreta. Confira em Configurações.",
                technicalDetails: "unauthorized: autenticação da API local rejeitada (HTTP 401/403)."
            )
        case APIError.missingAPIKey:
            return Presentation(
                headline: "Configure a chave da API em Configurações antes de continuar.",
                technicalDetails: "missingAPIKey: nenhuma chave foi definida ainda."
            )
        default:
            return Presentation(
                headline: "Aconteceu um problema inesperado.",
                technicalDetails: String(describing: error)
            )
        }
    }
}
