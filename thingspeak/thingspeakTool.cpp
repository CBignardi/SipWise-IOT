#include <iostream>
#include <string>
#include <sstream>
#include <map>
#include <curl/curl.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

// Funzione di callback per catturare la risposta HTTP
size_t WriteCallback(void *contents, size_t size, size_t nmemb, std::string *userp)
{
    size_t totalSize = size * nmemb;
    userp->append((char *)contents, totalSize);
    return totalSize;
}

// Esegue una richiesta HTTP GET
void performGet(const std::string &url, const std::string &canale)
{
    CURL *curl;
    CURLcode res;
    std::string readBuffer;

    curl = curl_easy_init();
    if (curl)
    {
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);

        res = curl_easy_perform(curl);

        if (res != CURLE_OK)
        {
            std::cerr << "Errore cURL (GET): " << curl_easy_strerror(res) << std::endl;
        }
        else
        {
            json dataJson = json::parse(readBuffer);

            std::cout << "--- Risposta GET ---\n"
                      << readBuffer << "\n--------------------\n";

            int maxIter = 4;
            if (canale == "TREND")
            {
                maxIter = 1;
            }

            for (int i = 0; i < maxIter; i++)
            {
                std::ostringstream sstr;
                sstr << "field" << i + 1;

                std::cout << dataJson["channel"][sstr.str()] << ": " << dataJson["feeds"][0][sstr.str()] << std::endl;
            }
        }
        curl_easy_cleanup(curl);
    }
}

// Esegue una richiesta HTTP POST
void performPost(const std::string &url, const std::string &postData)
{
    CURL *curl;
    CURLcode res;
    std::string readBuffer;

    curl = curl_easy_init();
    if (curl)
    {
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postData.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);

        res = curl_easy_perform(curl);

        if (res != CURLE_OK)
        {
            std::cerr << "Errore cURL (POST): " << curl_easy_strerror(res) << std::endl;
        }
        else
        {
            std::cout << "--- Risposta POST ---\n"
                      << readBuffer << "\n---------------------\n";
        }
        curl_easy_cleanup(curl);
    }
}

int main(int argc, char *argv[])
{
    // Controllo dei parametri a riga di comando
    if (argc < 3)
    {
        std::cout << "Uso corretto:\n";
        std::cout << "  Lettura (GET):  " << argv[0] << " <CANALE> GET\n";
        std::cout << "  Scrittura (POST): " << argv[0] << " <CANALE> POST <VALORE> ...\n\n";
        std::cout << "Canali disponibili: DATA, TREND, HUMAN\n";
        return 1;
    }

    std::string canale = argv[1];
    std::string metodo = argv[2];

    // Configurazione dei canali con URL di lettura e API Key di scrittura fornite
    struct ChannelConfig
    {
        std::string readUrl;
        std::string writeApiKey;
    };

    std::map<std::string, ChannelConfig> channels = {
        {"DATA", {"https://api.thingspeak.com/channels/3201982/feeds.json?api_key=PJBB45HC2Q7ZHLC0&results=1", "YDV7AL6M52XTB0F5"}},
        {"TREND", {"https://api.thingspeak.com/channels/3273136/feeds.json?api_key=0K5BVJE66A7QE20W&results=1", "I4VYATTE7GLX1YW3"}},
        {"HUMAN", {"https://api.thingspeak.com/channels/3287534/feeds.json?api_key=F4DPXNVX3OTXOVFJ&results=1", "FIOGK434FAPU4AKJ"}}};

    // Validazione del canale
    if (channels.find(canale) == channels.end())
    {
        std::cerr << "Errore: Canale '" << canale << "' non valido! Scegli tra DATA, TREND, HUMAN.\n";
        return 1;
    }

    // Esecuzione in base al metodo scelto
    if (metodo == "GET")
    {
        std::cout << "Leggendo dal canale " << canale << "...\n";
        performGet(channels[canale].readUrl, canale);
    }
    else if (metodo == "POST")
    {
        std::ostringstream sstr;
        std::cout << "Scrivendo sul canale " << canale << "; payload: ";
        for (int i = 0; i < argc - 3; i++)
        {
            sstr << "&field" << i + 1 << "=" << argv[i + 3];
        }
        std::cout << sstr.str() << std::endl;
        std::string postUrl = "https://api.thingspeak.com/update";
        std::string postData = "api_key=" + channels[canale].writeApiKey + sstr.str();
        performPost(postUrl, postData);
    }
    else
    {
        std::cerr << "Errore: Metodo '" << metodo << "' non valido! Usa GET o POST.\n";
        return 1;
    }

    return 0;
}