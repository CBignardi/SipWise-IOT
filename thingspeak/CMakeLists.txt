cmake_minimum_required(VERSION 3.10)
project(ThingSpeakClient CXX)

# Impostiamo lo standard C++11 (o superiore)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Cerchiamo la libreria cURL nel sistema
find_package(CURL REQUIRED)

# Aggiungiamo l'eseguibile
add_executable(tool thingspeakTool.cpp)

# Colleghiamo la libreria cURL al nostro eseguibile
target_link_libraries(tool PRIVATE CURL::libcurl)