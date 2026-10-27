#include <iostream>
#include <string>
#include <sstream>
#include <map>
#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include <time.h>

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
            std::cerr << "Error cURL (GET): " << curl_easy_strerror(res) << std::endl;
        }
        else
        {
            json dataJson = json::parse(readBuffer);

            std::cout << "--- Response GET ---\n"
                      << readBuffer << "\n--------------------\n";

            int maxIter = 4;
            if (canale == "TREND")
            {
                maxIter = 1;
            }
            if (canale == "HUMAN")
            {
                maxIter = 3;
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
            std::cerr << "Error cURL (POST): " << curl_easy_strerror(res) << std::endl;
        }
        else
        {
            std::cout << "--- Response POST ---\n"
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
        std::cout << "Correct use:\n";
        std::cout << "\tRead (GET):  " << argv[0] << " <CHANNEL> GET\n";
        std::cout << "\tWrite (POST): " << argv[0] << " <CHANNEL> POST <VALUE> <VALUE> ...\n\n";
        std::cout << "Channels available: DATA, TREND, HUMAN\n";
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
        std::cerr << "Error: Channel '" << canale << "' not valid! Choose from DATA, TREND, HUMAN.\n";
        return 1;
    }

    // Esecuzione in base al metodo scelto
    if (metodo == "GET")
    {
        std::cout << "Reading from the channel: " << canale << "...\n";
        performGet(channels[canale].readUrl, canale);
    }
    else if (metodo == "POST")
    {
        // Con "-t" il timestamp viene inserito in automatico (solo canale DATA)
        bool autoTs = (argc > 3 && std::string(argv[3]) == "-t" && canale == "DATA");
        int primo = autoTs ? 4 : 3;                                  // indice in argv del primo valore
        const int TS_FIELD = 2;                                      // field in cui scrivere il timestamp
        const long long now = static_cast<long long>(time(nullptr)); // secondi dal 1970 (UTC)

        std::ostringstream sstr;
        int field = 1; // prossimo field da scrivere
        bool tsInserito = false;

        for (int i = primo; i < argc; i++)
        {
            if (autoTs && !tsInserito && field == TS_FIELD)
            {
                sstr << "&field" << field++ << "=" << now;
                tsInserito = true;
            }
            sstr << "&field" << field++ << "=" << argv[i];
        }
        if (autoTs && !tsInserito) // pochi valori: il timestamp va in coda
            sstr << "&field" << field << "=" << now;

        std::cout << "Writing on the channel: " << canale
                  << "; payload: " << sstr.str() << std::endl;

        std::string postUrl = "https://api.thingspeak.com/update";
        std::string postData = "api_key=" + channels[canale].writeApiKey + sstr.str();
        std::cout << postData << std::endl;
        performPost(postUrl, postData);
    }
    else
    {
        std::cerr << "Errore: Metodo '" << metodo << "' non valido! Usa GET o POST.\n";
        return 1;
    }

    return 0;
}