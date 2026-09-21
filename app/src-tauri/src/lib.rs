// La ventana enciende su propio motor.
//
// Hasta el 2026-09-21 lo encendia el script del menu de DaVinci
// (`Workspace > Scripts > Vidorq`), que hacia dos cosas: arrancar el motor y abrir
// esta ventana. Ese menu dejo de existir para Python en Resolve Free 21.1: Blackmagic
// quito Python de la version gratis a proposito (verificado el 2026-09-21 en la guia
// de scripting que trae la propia instalacion y en xere.my/journal, 14-sep-2026), asi
// que el script ya no aparece y, sin el, el motor no se encendia nunca. Vidorq no
// podia ni abrirse.
//
// Ahora la ventana se basta sola: al abrirse mira si el motor contesta, y si no, lo
// arranca ella. La salida a MP4 no necesita Resolve para nada, asi que con esto
// Vidorq vuelve a funcionar entero para editar a MP4 aunque DaVinci no este abierto.

use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

const MOTOR: &str = "127.0.0.1:9877";

/// Si ya hay un motor escuchando. Se pregunta al puerto y no al proceso: puede
/// haberlo encendido otra ventana, o el propio menu de Resolve en una version que
/// todavia lo tenga, y arrancar un segundo seria pelearse por el mismo puerto.
fn motor_vivo() -> bool {
    let addr: SocketAddr = match MOTOR.parse() {
        Ok(a) => a,
        Err(_) => return false,
    };
    TcpStream::connect_timeout(&addr, Duration::from_millis(400)).is_ok()
}

/// Donde esta el motor y con que Python se arranca.
///
/// Lo escribe `resolve/instalar.ps1` en `%APPDATA%\Vidorq\resolve.json`, y es el
/// mismo archivo que usaba el menu de Resolve, asi que no hay dos sitios que puedan
/// decir cosas distintas. El BOM se quita a mano: PowerShell lo mete por defecto y
/// ya rompio una vez el lector de Python de la otra punta.
fn donde_esta() -> Option<(String, PathBuf)> {
    let appdata = std::env::var("APPDATA").ok()?;
    let conf = PathBuf::from(appdata).join("Vidorq").join("resolve.json");
    let texto = std::fs::read_to_string(conf).ok()?;
    let v: serde_json::Value = serde_json::from_str(texto.trim_start_matches('\u{feff}')).ok()?;
    let python = v.get("python")?.as_str()?.to_string();
    let home = PathBuf::from(v.get("home")?.as_str()?);
    Some((python, home.join("engine")))
}

/// Arranca el motor oculto, sin consola, y lo suelta.
///
/// Suelto a proposito (proceso aparte y grupo propio): es lo que ya hacia el
/// menu de Resolve, el motor vive mas que la ventana, y asi cerrarla a mitad de un
/// render no se lo lleva por delante. Si luego se abre otra ventana, encuentra el
/// motor ya encendido y no arranca otro.
///
/// `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` y no `| CREATE_NO_WINDOW`: la
/// combinacion con esta ultima es INVALIDA en Windows y el arranque falla sin
/// decir nada, que es exactamente como se paso una tarde entera el 2026-08-17.
fn encender_motor() {
    if motor_vivo() {
        return;
    }
    let Some((python, engine)) = donde_esta() else {
        // Sin configuracion no hay que hacer: la ventana ya enseña "el motor esta
        // apagado" y como encenderlo, que es mejor que fallar aqui en silencio.
        return;
    };
    let server = engine.join("server.py");
    if !server.exists() {
        return;
    }
    let mut cmd = Command::new(python);
    cmd.arg(server).current_dir(engine);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP);
    }
    let _ = cmd.spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|_app| {
            // En un hilo aparte: comprobar el puerto y arrancar Python no puede
            // retrasar que la ventana se pinte. La interfaz ya sabe esperar al
            // motor y reintentar mientras arranca.
            std::thread::spawn(encender_motor);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
